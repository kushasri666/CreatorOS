import unittest
from workflow import CRITERIA, run_pipeline, _validate_verifier_result

class LiveFake:
    mode = "live_mesh"
    def __init__(self): self.call_count=0; self.image_count=0; self.verifier=0; self.writer=0
    def ask(self, role, data):
        self.call_count += 1
        if role.startswith("Strategist"):
            return {"angle":"A practical product angle", "hook":"Try this", "audience":"customers", "format":"post", "cta":"Save it", "reason":"Fits the brief", "applied_learning_ids":[], "source_ids":["S1"]}
        if role.startswith("Writer"):
            self.writer += 1
            if self.writer < 3:
                claim = f"Our brew keeps coffee fresh for 30 days, version {self.writer}."
                return {"text":claim, "citations":[{"claim":claim,"source_ids":["S1"]}]}
            claim = "Our brew uses small-batch roasted beans."
            return {"text":claim, "citations":[{"claim":claim,"source_ids":["S2"]}]}
        if role.startswith("Editor"):
            # Scripted passing score for the live policy (not measured model quality).
            return {"scores":dict.fromkeys(CRITERIA,9.2),"edits":[],"reason":"Clear and on voice"}
        if role.startswith("Verifier"):
            self.verifier += 1
            if self.verifier == 1:
                return {"checks":[{"claim":data["draft"],"source_ids":["S1"],"verdict":"thin","reason":"Source does not establish duration"}]}
            return {"checks":[{"claim":"Our brew uses small-batch roasted beans.","source_ids":["S2"],"verdict":"supported","reason":"Directly stated in product facts","evidence":[{"source_id":"S2","quote":"Our brew uses small-batch roasted beans."}]}]}
        if role.startswith("Visual"):
            return {"prompt":"Coffee beans on a warm counter", "reason":"Product match"}
        raise AssertionError(role)
    def image(self, prompt): self.call_count+=1; self.image_count+=1; return "fixture-image"

class VerificationLoopTests(unittest.TestCase):
    def source(self, sid, excerpt):
        return {"source_id":sid,"source_type":"user_product_facts","title":"Product facts","excerpt":excerpt}
    def test_thin_claim_triggers_one_targeted_retry_and_correction(self):
        mesh=LiveFake();events=[];retrieval=[]
        def more(claims, existing):
            retrieval.append(claims)
            return [self.source("S2","Our brew uses small-batch roasted beans.")], []
        result=run_pipeline(mesh,"Promote our brew","linkedin",{"tone":"friendly"},[],lambda a,d:events.append((a,d)),generate_image=False,
            sources=[self.source("S1","Our brew uses freshly roasted beans.")],product={"name":"Our brew"},research_more=more)
        self.assertEqual(len(retrieval),1)
        self.assertIn("Our brew keeps coffee fresh for 30 days",retrieval[0][0])
        self.assertTrue(result["verification"]["passed"])
        self.assertTrue(result["grounded_report"]["passed"])
        self.assertTrue(result["approved"])
        self.assertEqual(result["grounded_report"]["claims"][0]["source_ids"],["S2"])
        self.assertEqual(result["text"],"Our brew uses small-batch roasted beans.")
        self.assertEqual([v["status"] for v in result["verification_history"]],["complete","complete"])
        self.assertIn("research_retrieval",[a for a,_ in events])
        self.assertIn("verification",[a for a,_ in events])
        self.assertLessEqual(mesh.call_count,10)
    def test_verifier_rejects_unknown_sources_and_claims_absent_from_draft(self):
        result=_validate_verifier_result({"checks":[{"claim":"Made up claim.","source_ids":["S99"],"verdict":"supported","reason":"looks right"}]},
            "Real draft.",[],[],{"S1"})
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][0]["verdict"],"unsupported")
    def test_uncleared_claim_keeps_content_unapproved(self):
        mesh=LiveFake()
        def more(claims, existing): return [],["No additional evidence"]
        # Force the correction's second check to remain thin.
        original=mesh.ask
        def ask(role,data):
            if role.startswith("Verifier") and mesh.verifier==1:
                return original(role,data)
            if role.startswith("Verifier"):
                mesh.call_count+=1
                return {"checks":[{"claim":"Our brew uses small-batch roasted beans.","source_ids":["S2"],"verdict":"thin","reason":"Source too vague"}]}
            return original(role,data)
        mesh.ask=ask
        result=run_pipeline(mesh,"Promote our brew","linkedin",{"tone":"friendly"},[],lambda a,d:None,generate_image=False,
            sources=[self.source("S1","Our brew uses freshly roasted beans.")],product={"name":"Our brew"},
            research_more=lambda claims,existing:([self.source("S2","Small-batch beans.")],[]))
        self.assertFalse(result["approved"])
        self.assertFalse(result["verification"]["passed"])

if __name__=="__main__": unittest.main()

