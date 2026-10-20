from decimal import Decimal
import unittest
from unittest.mock import Mock
from scripts.compare_models import CAP, Comparison, reserve, validate, public_report


class ComparisonBudgetTests(unittest.TestCase):
    def ledger(self):
        return dict(prices={"test/model":{"input":"0.4","output":"1.6"}},calls=[],starting_balance_usd="1")

    def test_all_calls_share_one_ceiling_including_unsettled_failures(self):
        ledger=self.ledger()
        bound=reserve(ledger,"test/model",{"prompt":"test"},1000)
        ledger["calls"]=[{"reserved_usd":"0.749","status":"failed_or_unknown"}]
        with self.assertRaises(RuntimeError):
            reserve(ledger,"test/model",{"prompt":"test"},1000)
        self.assertLess(Decimal(bound),CAP)

    def test_exhausted_budget_blocks_generation_before_post(self):
        client=Mock()
        client.get.return_value.raise_for_status.return_value.json.return_value={"balance_usd":"1"}
        ledger=self.ledger()
        ledger["calls"]=[{"model":"other","task":"old","reserved_usd":"0.749"}]
        with self.assertRaises(RuntimeError):
            Comparison(client,ledger).call("test/model","writer","Write JSON",{},1000)
        client.post.assert_not_called()

    def test_writer_quality_contract_requires_all_seven_slides(self):
        self.assertFalse(validate("writer",{"text":"Caption","slides":["one"]}))
        self.assertTrue(validate("writer",{"text":"Caption","slides":[str(i) for i in range(7)]}))

    def test_public_report_excludes_account_metadata_and_headers(self):
        result=public_report({"starting_balance_usd":"private","ending_balance_usd":"private", "calls":[
            {"billing":{"request_headers":{"Authorization":"private"},"event":{"key_id":"private","cost_usd":"0.001"},"attempts":[]}}]})
        self.assertNotIn("private",str(result))
        self.assertEqual(result["calls"][0]["billing"]["cost_usd"],"0.001")
