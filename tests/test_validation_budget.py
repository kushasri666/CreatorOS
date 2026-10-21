"""Budget boundaries before any network generation; independent of Mesh credentials."""
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import httpx
from validation_budget import BASE,CAP,Budget,bound,liability


class ValidationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.prices={'test/text':dict(pricing_unit='per_1m_tokens',prompt_usd_per_1m='.4',completion_usd_per_1m='1.6'),
            'test/image':dict(pricing_unit='per_image',image_output_usd_per_image='.0032')}
        self.ledger=dict(calls=[],prices=self.prices,starting_balance_usd='1')
        self.metadata=Mock();self.metadata.get.return_value.raise_for_status.return_value.json.return_value={'balance_usd':'1'}
        self.guard=Budget(Path(self.temp.name)/'ledger.json',self.ledger,self.metadata)
        self.body=dict(model='test/text',messages=[{'role':'user','content':'Test'}],max_tokens=1000)
    def tearDown(self):self.temp.cleanup()

    def request(self):return httpx.Request('POST',BASE+'/chat/completions',json=self.body)

    def test_ceiling_is_strictly_lower_than_authorization(self):self.assertLess(CAP,Decimal('.75'))

    def test_only_finalized_successes_release_reserved_headroom(self):
        self.assertEqual(liability([dict(status='response_received',billing_status='success',settled_usd='.01',reserved_usd='.5')]),Decimal('.01'))
        self.assertEqual(liability([dict(status='failed_response',billing_status='success',settled_usd='0',reserved_usd='.5')]),Decimal('.5'))
        self.assertEqual(liability([dict(status='reserved_or_unknown',reserved_usd='.5')]),Decimal('.5'))
        self.assertEqual(liability([dict(status='response_received',billing_status='usage_bound',usage_bound_usd='.03',reserved_usd='.5')]),Decimal('.03'))
        self.assertEqual(liability([dict(status='failed_response',billing_status='usage_bound',usage_bound_usd='.03',reserved_usd='.5')]),Decimal('.5'))

    def test_cumulative_failures_are_never_refunded(self):
        self.ledger['calls']=[dict(status='failed_response',reserved_usd=str(CAP-Decimal('.001')))]
        with self.assertRaises(ValueError):self.guard.before(self.request())
        self.metadata.get.assert_not_called()
        self.assertEqual(len(self.ledger['calls']),1)

    def test_unknown_request_prevents_blind_retry(self):
        self.guard.before(self.request())
        with self.assertRaises(ValueError):self.guard.before(self.request())
        self.assertEqual(len(self.ledger['calls']),1)
        persisted=json.loads(self.guard.path.read_text())
        self.assertEqual(persisted['calls'][0]['status'],'reserved_or_unknown')

    def test_failed_response_keeps_full_reservation(self):
        self.guard.before(self.request());reservation=self.ledger['calls'][0]['reserved_usd']
        self.guard.after(httpx.Response(500,json={'error':'provider failure'}))
        self.assertEqual(self.ledger['calls'][0]['reserved_usd'],reservation)
        self.assertEqual(self.ledger['calls'][0]['status'],'failed_response')

    def test_balance_guard_accounts_for_external_spending(self):
        self.metadata.get.return_value.raise_for_status.return_value.json.return_value={'balance_usd':str(Decimal(1)-CAP)}
        with self.assertRaises(ValueError):self.guard.before(self.request())
        self.assertEqual(self.ledger['calls'],[])

    def test_wrong_host_unknown_route_and_unbounded_output_are_blocked(self):
        with self.assertRaises(ValueError):self.guard.before(httpx.Request('POST','https://example.com/v1/chat/completions',json=self.body))
        with self.assertRaises(ValueError):bound(self.body,'/v1/video/generations',self.prices)
        with self.assertRaises(ValueError):bound(dict(self.body,max_tokens=None),'/v1/chat/completions',self.prices)
        with self.assertRaises(ValueError):bound(dict(self.body,max_tokens=2000),'/v1/chat/completions',self.prices)

    def test_unknown_image_pricing_cannot_spend(self):
        prices={'test/image':dict(pricing_unit='per_1m_tokens',image_output_usd_per_image='8')}
        with self.assertRaises(ValueError):bound(dict(model='test/image',size='1024x1024'),'/v1/images/generations',prices)
        self.assertLess(bound(dict(model='test/image',size='1024x1024'),'/v1/images/generations',self.prices),Decimal('.03'))

    def test_only_one_image_across_all_phases(self):
        request=httpx.Request('POST',BASE+'/images/generations',json=dict(model='test/image',size='1024x1024'))
        self.guard.before(request);self.guard.after(httpx.Response(200,json={'data':[]}))
        with self.assertRaises(ValueError):self.guard.before(request)
        self.assertEqual(len(self.ledger['calls']),1)

    def test_extended_run_preserves_shared_dollar_ceiling(self):
        guard=Budget(self.guard.path,self.ledger,self.metadata,call_limit=110,image_limit=3)
        self.ledger['calls']=[dict(status='failed_response',reserved_usd=str(CAP-Decimal('.001')))]
        with self.assertRaises(ValueError):guard.before(self.request())
        self.assertEqual(len(self.ledger['calls']),1)
        with self.assertRaises(ValueError):Budget(self.guard.path,self.ledger,self.metadata,call_limit=241)
        with self.assertRaises(ValueError):Budget(self.guard.path,self.ledger,self.metadata,image_limit=6)
