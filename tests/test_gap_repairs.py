"""Controls for actual gap repairs; no model calls or customer data."""
import base64
import io
import unittest
from PIL import Image,ImageStat
from source_policy import blocking_conflicts,review_sources
from verification_contract import units,resolve,packet
from workflow import _validate_verifier_result
from visual_composer import compose
from prompt_policy import compact_data


class GapRepairTests(unittest.TestCase):
    def test_context_compaction_removes_only_identical_complete_owner_facts(self):
        facts='Product supports US customers on the annual plan.'
        original=dict(product=dict(user_provided_facts=facts),research=dict(findings=[dict(claim=facts)]))
        self.assertNotIn('user_provided_facts',compact_data('Writer:',original)['product'])
        self.assertEqual(original['product']['user_provided_facts'],facts)
        similar=dict(product=dict(user_provided_facts=facts),research=dict(findings=[dict(claim=facts.lower())]))
        self.assertEqual(compact_data('Writer:',similar)['product']['user_provided_facts'],facts)

    def test_exact_caption_composition_is_local_sharp_and_does_not_truncate(self):
        raw=io.BytesIO();Image.new('RGB',(1024,1024),'#bda7dc').save(raw,'PNG')
        source='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
        result=compose(source,'LearnAIwithSachit','Build, deploy and learn practical AI tools.')
        with Image.open(io.BytesIO(base64.b64decode(result.split(',',1)[1]))) as image:
            self.assertEqual(image.size,(1080,1080))
            self.assertGreater(sum(ImageStat.Stat(image.crop((60,110,1018,400))).var),100)
        with self.assertRaises(ValueError):compose(source,'Brand','X'*450)

    def test_explicit_packaging_attribution_and_disagreement_do_not_hide_a_value(self):
        sources=[dict(source_id=s,source_type='user_product_facts',excerpt=f'Brew Mini has {n} grind settings.') for s,n in [('S1',12),('S2',10)]]
        conflicts=review_sources(sources)['conflicts']
        self.assertTrue(blocking_conflicts('Brew Mini has 12 grind settings; save this report.',['S1'],conflicts))
        self.assertFalse(blocking_conflicts('The packaging lists 10 grind settings.',['S2'],conflicts))
        self.assertFalse(blocking_conflicts('These documents disagree about the setting count.',['S1','S2'],conflicts))

    def test_second_nonnumeric_clause_needs_its_own_classification(self):
        text='Brew Mini includes a cleaning brush, and it is waterproof.'
        data=dict(draft=text,slides=[],sources=[dict(source_id='S1',excerpt='Brew Mini includes a cleaning brush.')])
        candidates,receipts=packet(data);manifest=units(text,[])
        self.assertEqual(len(manifest),2)
        factual=next(k for k,v in candidates.items() if v=='Brew Mini includes a cleaning brush')
        receipt=next(k for k,v in receipts.items() if v['quote']=='Brew Mini includes a cleaning brush.')
        raw=dict(checks=[dict(candidate_id=factual,source_ids=['S1'],verdict='supported',reason='Exact source statement',evidence=[dict(receipt_id=receipt)])],conflicts=[],
            coverage=[dict(unit_id='U1',kind='factual',candidate_ids=[factual],reason='Supported brush feature')])
        resolved=resolve(raw,candidates,receipts,manifest)
        self.assertFalse(_validate_verifier_result(resolved,text,[],[],data['sources'])['passed'])
