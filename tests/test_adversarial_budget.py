"""Hard-budget adversarial regressions. All metadata is mocked; no network/AI."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import httpx
from validation_budget import BASE, Budget, CAP, bound, save


class AdversarialBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.prices={'test/text':dict(pricing_unit='per_1m_tokens',prompt_usd_per_1m='.4',completion_usd_per_1m='1.6')}
        self.body=dict(model='test/text',messages=[dict(role='user',content='Test')],max_tokens=1000)
        self.base=dict(authorization='fixture shared authorization',starting_balance_usd='1',prices=self.prices,calls=[])
        self.metadata=Mock()
        self.metadata.get.return_value.raise_for_status.return_value.json.return_value={'balance_usd':'1'}

    def tearDown(self):self.temp.cleanup()

    def guard(self,ledger=None,path=None):
        return Budget(path or self.root/'ledger.json',ledger if ledger is not None else deepcopy(self.base),self.metadata,
            state_dir=self.root/'guards',search_root=self.root)

    def request(self,**extra):return httpx.Request('POST',BASE+'/chat/completions',json=dict(self.body,**extra))

    def test_multiple_completions_unknown_costly_options_and_multimodal_inputs_fail_closed(self):
        for extra in (dict(n=2),dict(n=True),dict(max_completion_tokens=100000),dict(modalities=['audio']),
            dict(audio={'voice':'alloy'}),dict(web_search_options={}),dict(service_tier='priority'),
            dict(messages=[dict(role='user',content=[dict(type='image_url',image_url={'url':'https://example.invalid/image.png'})])]),
            dict(messages=[dict(role='user',content=[dict(type='text',text='Text blocks require separate review')])])):
            with self.subTest(extra=list(extra)):
                with self.assertRaises(ValueError):bound(dict(self.body,**extra),'/v1/chat/completions',self.prices)

    def test_plain_json_text_generation_remains_allowed_and_rates_must_be_finite(self):
        self.assertGreater(bound(dict(self.body,response_format={'type':'json_object'}),'/v1/chat/completions',self.prices),0)
        for value in ('NaN','Infinity','-1'):
            prices=deepcopy(self.prices);prices['test/text']['prompt_usd_per_1m']=value
            with self.assertRaises(ValueError):bound(self.body,'/v1/chat/completions',prices)

    def test_nondefault_port_and_userinfo_are_rejected_before_metadata(self):
        for url in ('https://api.meshapi.ai:8443/v1/chat/completions','https://user@api.meshapi.ai/v1/chat/completions'):
            with self.assertRaises(ValueError):self.guard().before(httpx.Request('POST',url,json=self.body))
        self.metadata.get.assert_not_called()

    def test_two_instances_cannot_spend_the_same_remaining_allowance(self):
        reservation=bound(self.body,'/v1/chat/completions',self.prices)
        ledger=dict(self.base,calls=[dict(index=1,status='failed_response',reserved_usd=str(CAP-reservation*Decimal('1.5')))])
        one,two=self.guard(deepcopy(ledger)),self.guard(deepcopy(ledger))
        one.before(self.request())
        persisted=one.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'owns this validation budget family'):two.before(self.request())
        self.assertEqual(one.path.read_bytes(),persisted)
        self.assertEqual(len(json.loads(persisted)['calls']),2)
        one.after(httpx.Response(500,json={'error':'fixture'}))

    def test_unknown_transport_outcome_keeps_family_blocked_across_instances(self):
        one=self.guard();one.before(self.request())
        two=self.guard(deepcopy(self.base),self.root/'continuation.json')
        with self.assertRaisesRegex(ValueError,'owns this validation budget family'):two.before(self.request())
        self.assertTrue(one.lease.exists())

    def test_failed_admission_releases_lease_and_does_not_consume_request(self):
        one=self.guard();one.call_limit=1
        one.ledger['calls']=[dict(index=1,status='failed_response',reserved_usd='.01')]
        with self.assertRaisesRegex(ValueError,'call-count ceiling'):one.before(self.request())
        self.assertFalse(one.lease.exists());self.assertEqual(len(one.ledger['calls']),1)

    def test_metadata_failure_before_admission_releases_lease_without_reserving(self):
        one=self.guard();self.metadata.get.side_effect=RuntimeError('Fixture metadata unavailable')
        with self.assertRaisesRegex(RuntimeError,'metadata unavailable'):one.before(self.request())
        self.assertFalse(one.lease.exists());self.assertEqual(one.ledger['calls'],[])

    def test_equivalent_decimal_formatting_does_not_split_a_budget_family(self):
        one=self.guard();other=deepcopy(self.base);other['starting_balance_usd']='1.000';other['user_cap_usd']='0.7500'
        two=self.guard(other,self.root/'other.json')
        self.assertEqual(one.family_id,two.family_id)
        one.before(self.request())
        with self.assertRaisesRegex(ValueError,'owns this validation budget family'):two.before(self.request())
        one.after(httpx.Response(500,json={'error':'fixture'}))

    def test_response_releases_lease_and_sequential_same_ledger_calls_work(self):
        one=self.guard();one.before(self.request());one.after(httpx.Response(200,json={'choices':[]}))
        self.assertFalse(one.lease.exists())
        one.before(self.request());one.after(httpx.Response(500,json={'error':'fixture'}))
        self.assertFalse(one.lease.exists());self.assertEqual(len(one.ledger['calls']),2)

    def test_existing_newer_continuation_blocks_stale_parent_before_first_migration(self):
        parent=self.root/'parent'/'ledger.json';child=self.root/'child'/'ledger.json'
        old=deepcopy(self.base);old['calls']=[dict(index=1,status='failed_response',reserved_usd='.01')]
        save(parent,old)
        new=deepcopy(old);new['parent_ledger_sha256']=hashlib.sha256(parent.read_bytes()).hexdigest()
        new['calls'].append(dict(index=2,status='failed_response',reserved_usd='.01'));save(child,new)
        guard=self.guard(old,parent)
        with self.assertRaisesRegex(ValueError,'Stale validation ledger'):guard.before(self.request())
        self.assertFalse(guard.lease.exists());self.assertEqual(len(json.loads(parent.read_text())['calls']),1)

    def test_latest_continuation_cannot_be_replaced_by_a_stale_in_memory_snapshot(self):
        old=deepcopy(self.base);one=self.guard(old);stale=deepcopy(old)
        one.before(self.request());one.after(httpx.Response(200,json={'choices':[]}))
        unchanged=one.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'Stale validation ledger'):self.guard(stale).before(self.request())
        self.assertEqual(one.path.read_bytes(),unchanged)

    def test_an_independent_process_cannot_bypass_the_file_lease(self):
        one=self.guard();one.before(self.request())
        fixture=self.root/'child-input.json';save(fixture,self.base)
        code='''
import json,sys
from pathlib import Path
from unittest.mock import Mock
import httpx
from validation_budget import Budget,BASE
root=Path(sys.argv[1]); ledger=json.loads((root/'child-input.json').read_text())
guard=Budget(root/'other.json',ledger,Mock(),state_dir=root/'guards',search_root=root)
try:guard.before(httpx.Request('POST',BASE+'/chat/completions',json=dict(model='test/text',messages=[dict(role='user',content='Test')],max_tokens=1000)))
except ValueError as exc:
    assert 'owns this validation budget family' in str(exc)
    print('child blocked before metadata')
else:raise AssertionError('Overlapping paid request admitted')
'''
        result=subprocess.run([sys.executable,'-c',code,str(self.root)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('child blocked before metadata',result.stdout)
        one.after(httpx.Response(500,json={'error':'fixture'}))


if __name__=='__main__':unittest.main()
