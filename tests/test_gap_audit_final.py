"""Independent final source-recheck contract audit. Scripted responses, no AI."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reverification
import storage
from workflow import _validate_verifier_result


FACT='Brew Mini includes a cleaning brush.'


class ScriptedVerifier:
    def __init__(self,on_ask=None):
        self.call_count=0
        self.on_ask=on_ask
    def ask(self,role,data):
        self.call_count+=1
        if self.on_ask:self.on_ask()
        return dict(checks=[dict(claim=FACT,source_ids=['S1'],verdict='supported',
            reason='Synthetic support verdict.',evidence=[dict(source_id='S1',quote=FACT)])],conflicts=[])


class FinalGapAuditTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).parents[1]/'data'/'evaluation-test-tmp'
        root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='gap-audit-',dir=root)
        self.addCleanup(self.temp.cleanup)
        token=storage.database_override.set(str(Path(self.temp.name)/'audit.db'))
        self.addCleanup(storage.database_override.reset,token)
        self.environment=patch.dict(os.environ,dict(MESH_ENABLE_PAID='0',CREATOROS_MODE='live'))
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.post=storage.save('post',dict(status='needs_review',approved=False,
            brand_id='synthetic-audit',platform='linkedin',text=FACT,slides=[],
            sources=[dict(source_id='S1',title='Synthetic product facts',source_type='user_product_facts',excerpt=FACT)],
            citations=[dict(claim=FACT,source_ids=['S1'])],drafts=[FACT],slide_versions=[[]],
            selected_draft_index=0,assessments=[dict(ready=True,action='accept')],
            reviews=[dict(average=9.5)],editorial_checks=[dict(checks=dict(length=True))],
            evidence_review=dict(conflicts=[]),verification_history=[]))

    def test_supported_recheck_preserves_matching_selected_editor_lineage(self):
        result=reverification.recheck(self.post['id'],'audit-matching-lineage',lambda:ScriptedVerifier())
        self.assertTrue(result['approved'])

    def test_other_draft_ready_does_not_approve_selected_editorial_failure(self):
        post=copy.deepcopy(self.post)
        post.update(drafts=[FACT,'An unrelated editorial draft.'],slide_versions=[[],[]],
            assessments=[dict(ready=False,action='needs_review'),dict(ready=True,action='accept')])
        storage.save('post',post,post['id'])
        result=reverification.recheck(post['id'],'audit-wrong-last-assessment',lambda:ScriptedVerifier())
        self.assertFalse(result.get('approved',False))
        self.assertEqual(storage.get(post['id'])['status'],'needs_review')

    def test_changed_saved_text_without_matching_reviewed_draft_is_not_approved(self):
        post=copy.deepcopy(self.post)
        post['drafts']=['Old wording reviewed by the editor.']
        storage.save('post',post,post['id'])
        result=reverification.recheck(post['id'],'audit-stale-editor-lineage',lambda:ScriptedVerifier())
        self.assertFalse(result.get('approved',False))
        self.assertEqual(storage.get(post['id'])['status'],'needs_review')

    def test_selected_editor_lineage_change_during_call_is_stale(self):
        post=copy.deepcopy(self.post)
        post.update(drafts=[FACT,FACT],slide_versions=[[],[]],assessments=[dict(ready=True),dict(ready=False)])
        storage.save('post',post,post['id'])
        def change_selection():
            current=storage.get(post['id'])
            storage.save('post',dict(current,selected_draft_index=1),post['id'])
        result=reverification.recheck(post['id'],'audit-selected-index-race',lambda:ScriptedVerifier(change_selection))
        self.assertEqual(result['status'],'stale')
        self.assertEqual(storage.get(post['id'])['selected_draft_index'],1)
        self.assertFalse(storage.get(post['id'])['approved'])

    def test_acceptance_context_changes_during_call_are_not_overwritten(self):
        for field,value in [('platform','instagram'),
                            ('evidence_review',dict(conflicts=[dict(id='new-conflict',status='unresolved')])),
                            ('editorial_checks',[dict(checks=dict(length=False))])]:
            with self.subTest(field=field):
                post=copy.deepcopy(self.post)
                post=storage.save('post',post)
                def change_context():
                    current=storage.get(post['id'])
                    storage.save('post',dict(current,**{field:value}),post['id'])
                result=reverification.recheck(post['id'],'audit-context-'+field,lambda:ScriptedVerifier(change_context))
                self.assertEqual(result['status'],'stale')
                self.assertEqual(storage.get(post['id'])[field],value)
                self.assertFalse(storage.get(post['id'])['approved'])

    def test_missing_editor_lineage_cannot_create_approval(self):
        post=copy.deepcopy(self.post)
        for key in ('drafts','slide_versions','selected_draft_index'):
            post.pop(key)
        storage.save('post',post,post['id'])
        result=reverification.recheck(post['id'],'audit-no-editor-lineage',lambda:ScriptedVerifier())
        self.assertFalse(result['approved'])
        self.assertFalse(result['editorial_ready'])
        self.assertIn('Missing selected editorial lineage',result['editorial_reason'])
        self.assertEqual(storage.get(post['id'])['status'],'needs_review')

    def test_verifier_failure_counts_attempt_and_never_updates_approval(self):
        mesh=ScriptedVerifier()
        def failure(role,data):
            mesh.call_count+=1
            raise ValueError('Synthetic invalid gateway response')
        mesh.ask=failure
        with self.assertRaisesRegex(ValueError,'invalid gateway response'):
            reverification.recheck(self.post['id'],'audit-failed-verifier-count',lambda:mesh)
        operation=storage.listing('verification_recheck')[0]
        self.assertEqual(operation['status'],'failed')
        self.assertEqual(operation['ai_calls'],1)
        self.assertEqual(storage.get(self.post['id']),self.post)

    def test_nonexact_writer_annotation_is_not_silently_normalized_by_casefold(self):
        fact='Our service supports US users.'
        result=_validate_verifier_result(dict(checks=[dict(claim=fact,source_ids=['S1'],
            verdict='supported',reason='Synthetic support verdict.',evidence=[dict(source_id='S1',quote=fact)])]),
            fact,[],[dict(claim='Our service supports us users.',source_ids=['S1'])],
            [dict(source_id='S1',excerpt=fact)])
        self.assertFalse(result['passed'])


if __name__=='__main__':
    unittest.main()
