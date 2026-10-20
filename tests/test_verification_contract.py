import unittest
from verification_contract import packet,resolve,canonical_claim
from workflow import _validate_verifier_result


class VerificationContractTests(unittest.TestCase):
    def setUp(self):
        self.data=dict(draft='Brew offers 12 settings, so find your favourite. Save this guide!',slides=[],
            sources=[dict(source_id='S1',excerpt='Brew has 12 settings. It includes a brush.')])
        self.candidates,self.receipts=packet(self.data)
    def result(self,receipt):
        candidate=next(k for k,v in self.candidates.items() if v=='Brew offers 12 settings')
        return dict(checks=[dict(candidate_id=candidate,source_ids=['S1'],verdict='supported',reason='Direct specification',evidence=[dict(receipt_id=receipt)])],conflicts=[])
    def test_resolves_verbatim_text_without_changing_verdict_or_numbers(self):
        rid=next(k for k,v in self.receipts.items() if v['quote']=='Brew has 12 settings.')
        result=resolve(self.result(rid),self.candidates,self.receipts)
        self.assertEqual(result['checks'][0]['claim'],'Brew offers 12 settings')
        checked=_validate_verifier_result(result,self.data['draft'],[],[],self.data['sources'])
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['checks'][0]['evidence'][0]['quote'],'Brew has 12 settings.')
    def test_unknown_candidate_or_receipt_cannot_pass(self):
        raw=self.result('invented')
        resolved=resolve(raw,self.candidates,self.receipts)
        self.assertFalse(_validate_verifier_result(resolved,self.data['draft'],[],[],self.data['sources'])['passed'])
        raw['checks'][0]['candidate_id']='invented'
        resolved=resolve(raw,self.candidates,self.receipts)
        self.assertFalse(_validate_verifier_result(resolved,self.data['draft'],[],[],self.data['sources'])['passed'])
    def test_terminal_punctuation_only_and_no_word_or_number_repair(self):
        self.assertEqual(canonical_claim('Brew offers 12 settings.',[self.data['draft']]),'Brew offers 12 settings')
        self.assertEqual(canonical_claim('Brew offers 20 settings.',[self.data['draft']]),'Brew offers 20 settings.')
        self.assertEqual(canonical_claim('Brew has 12 settings.',[self.data['draft']]),'Brew has 12 settings.')
    def test_typed_ids_do_not_turn_unsupported_into_supported(self):
        rid=next(iter(self.receipts))
        raw=self.result(rid);raw['checks'][0]['verdict']='unsupported'
        resolved=resolve(raw,self.candidates,self.receipts)
        self.assertFalse(_validate_verifier_result(resolved,self.data['draft'],[],[],self.data['sources'])['passed'])

    def test_split_receipts_are_merged_without_losing_a_cited_source(self):
        text='Brew has 12 settings.'
        sources=[dict(source_id=s,excerpt=text) for s in ['S1','S2']]
        raw=dict(checks=[dict(claim=text,source_ids=[s],verdict='supported',reason='Exact source quote',evidence=[dict(source_id=s,quote=text)]) for s in ['S1','S2']])
        result=_validate_verifier_result(raw,text,[],[dict(claim=text,source_ids=['S1','S2'])],sources)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']),1)
        self.assertEqual(result['checks'][0]['source_ids'],['S1','S2'])
        self.assertEqual(len(result['checks'][0]['evidence']),2)

    def test_merging_duplicate_checks_does_not_hide_a_rejection(self):
        text='Brew has 12 settings.'
        sources=[dict(source_id='S1',excerpt=text)]
        raw=dict(checks=[dict(claim=text,source_ids=['S1'],verdict='supported',reason='Quote',evidence=[dict(source_id='S1',quote=text)]),
            dict(claim=text,source_ids=['S1'],verdict='unsupported',reason='Conflicting finding',evidence=[])])
        result=_validate_verifier_result(raw,text,[],[dict(claim=text,source_ids=['S1'])],sources)
        self.assertFalse(result['passed'])
        self.assertEqual(result['checks'][0]['verdict'],'unsupported')
