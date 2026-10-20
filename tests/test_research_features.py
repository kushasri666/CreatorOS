"""Executable graph, source policy, exports and follow-ups; no live model calls."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent_graph import StateGraph,NODES,definition
from source_policy import quality,review_sources,validate_semantic_conflicts,blocking_conflicts
from reports import render_report
from workflow import run_pipeline,Mesh
from tests.test_verification_loop import LiveFake
import followups
import storage


def source(sid,text,kind="official_product_page"):
    return dict(source_id=sid,source_type=kind,title="Product evidence",url="https://brand.example/product",excerpt=text)


class ResearchGraphTests(unittest.TestCase):
    def test_disputed_value_forces_real_retry_and_attributed_correction(self):
        class ConflictGateway:
            mode="live_mesh"
            def __init__(self):self.call_count=0;self.writers=0
            def ask(self,role,data):
                self.call_count+=1
                if role.startswith("Strategist"):return dict(angle="Product modes",applied_learning_ids=[],source_ids=["S1"])
                if role.startswith("Writer"):
                    self.writers+=1
                    claim="Brew has 8 modes." if self.writers<3 else "The primary specification lists 12 modes."
                    return dict(text=claim+(" Save this." if self.writers==2 else ""),citations=[dict(claim=claim,source_ids=["S1" if self.writers<3 else "S2"])])
                if role.startswith("Editor"):return dict(scores=dict.fromkeys(("hook","clarity","voice","platform","cta"),9),edits=[],reason="Clear product copy")
                if role.startswith("Verifier"):
                    before="Brew has 8 modes." in data["draft"]
                    return dict(checks=[dict(claim="Brew has 8 modes." if before else "The primary specification lists 12 modes.",source_ids=["S1" if before else "S2"],
                        verdict="supported",reason="Quote exists",evidence=[dict(source_id="S1" if before else "S2",quote="Brew has 8 modes." if before else "Brew has 12 modes.")])],conflicts=[])
                return dict(prompt="Brew product illustration",reason="Matching visual prompt")
        retries=[];gateway=ConflictGateway()
        result=run_pipeline(gateway,"Brew features","linkedin",{},[],lambda a,d:None,generate_image=False,
            sources=[source("S1","Brew has 8 modes.","third_party_blog"),source("S2","Brew has 12 modes.")],
            research_more=lambda claims,existing:(retries.append(claims) or [],[]))
        self.assertEqual(len(retries),1);self.assertTrue(result["approved"])
        self.assertEqual(result["evidence_review"]["conflicts"][0]["status"],"unresolved")
        self.assertEqual(result["text"],"The primary specification lists 12 modes.")
        self.assertEqual(result["verification_history"][0]["checks"][0]["verdict"],"thin")

    def test_unsupported_verification_executes_research_edge_and_recheck(self):
        mesh=LiveFake();original=mesh.ask;retrieval=[]
        def ask(role,data):
            result=original(role,data)
            if role.startswith("Verifier") and mesh.verifier==1:result["checks"][0]["verdict"]="unsupported"
            return result
        mesh.ask=ask
        def more(claims,existing):
            retrieval.append(claims);return [source("S2","Our brew uses small-batch roasted beans.")],[]
        result=run_pipeline(mesh,"Our brew","linkedin",{},[],lambda a,d:None,generate_image=False,
            sources=[source("S1","Freshly roasted beans.")],research_more=more)
        self.assertEqual(len(retrieval),1)
        pairs=[(t["node"],t["next"]) for t in result["graph_trace"]]
        self.assertIn(("verifier","research_retry"),pairs)
        self.assertIn(("research_retry","source_review"),pairs)
        self.assertIn(("writer_correction","verifier"),pairs)
        self.assertTrue(result["approved"])
        self.assertLessEqual(mesh.call_count,10)

    def test_initial_retrieval_is_executed_inside_graph(self):
        called=[]
        def initial():called.append(True);return [source("S1","Freshly roasted beans.")],[]
        def more(claims,existing):return [source("S2","Our brew uses small-batch roasted beans.")],[]
        result=run_pipeline(LiveFake(),"Our brew","linkedin",{},[],lambda a,d:None,generate_image=False,
            research_initial=initial,research_more=more)
        self.assertEqual(called,[True]);self.assertEqual(result["graph_trace"][0]["node"],"research")

    def test_graph_rejects_undeclared_edges_and_bounds_cycles(self):
        handlers={n.name:(lambda state:None) for n in NODES}
        handlers["research"]=lambda state:"finish"
        with self.assertRaises(ValueError):StateGraph(handlers,lambda a,d:None).run({})
        routes=dict(research="source_review",source_review="strategist",strategist="writer",writer="editor",editor="writer")
        for key,next_node in routes.items():handlers[key]=lambda state,to=next_node:to
        with self.assertRaisesRegex(ValueError,"bounded execution"):StateGraph(handlers,lambda a,d:None).run({})


class SourcePolicyTests(unittest.TestCase):
    def test_verifier_compaction_reuses_exact_source_text_without_duplicate_context(self):
        from prompt_policy import compact_data
        original=source("S1","Brew has 12 modes.  Exact quotation spacing stays intact.")
        compact=compact_data("Verifier: check saved sources",dict(sources=[original],voice={"tone":"warm"},history=["not evidence"],
            research=dict(findings=[original],conflicts=[]),writer_citations=[]))
        self.assertEqual(compact["sources"][0]["excerpt"],original["excerpt"])
        self.assertNotIn("findings",compact["research"]);self.assertNotIn("history",compact);self.assertNotIn("voice",compact)

    def test_primary_over_blog_with_scope_and_visible_basis(self):
        self.assertGreater(quality(source("S1","Evidence"))["score"],quality(source("S2","Evidence","third_party_blog"))["score"])
        self.assertEqual(quality(source("S3","Observations","social_account_metrics"))["scope"],"account_and_window_only")
        self.assertTrue(quality(source("S1","Evidence"))["reason"])

    def test_disagreements_remain_flagged_despite_primary_preference(self):
        sources=[source("S1","Brew Mini has 8 grind settings.","third_party_blog"),source("S2","Brew Mini has 12 grind settings.")]
        review=review_sources(sources);self.assertEqual(len(review["conflicts"]),1)
        conflict=review["conflicts"][0];self.assertEqual(conflict["preferred_source_id"],"S2")
        self.assertEqual(conflict["status"],"unresolved")
        self.assertTrue(blocking_conflicts("Brew Mini has 8 grind settings.",["S1"],review["conflicts"]))
        self.assertFalse(blocking_conflicts("The primary specification lists 12 grind settings.",["S2"],review["conflicts"]))

    def test_unrelated_entities_are_not_contradictions(self):
        self.assertFalse(review_sources([source("S1","Brew Mini has 8 modes."),source("S2","Brew Pro has 12 modes.")])["conflicts"])

    def test_semantic_conflicts_require_two_real_quoted_sources(self):
        sources=[source("S1","Dishwasher safe."),source("S2","Hand-wash only.")]
        raw=[dict(subject="Washing instructions",reason="Instructions disagree",evidence=[dict(source_id="S1",quote="Dishwasher safe."),dict(source_id="S2",quote="Hand-wash only.")])]
        conflicts,error=validate_semantic_conflicts(raw,sources)
        self.assertIsNone(error);self.assertEqual(conflicts[0]["status"],"unresolved")
        raw[0]["evidence"][1]["quote"]="Invented quote"
        self.assertIsNotNone(validate_semantic_conflicts(raw,sources)[1])


class FollowupFake:
    def __init__(self):self.call_count=0;self.contexts=[]
    def ask(self,role,data):
        self.call_count+=1;self.contexts.append(data)
        if role.startswith("Follow-up"):
            return dict(text="Brew has two modes.",citations=[dict(claim="Brew has two modes.",source_ids=["S1"])],limitations=[])
        return dict(checks=[dict(claim="Brew has two modes.",source_ids=["S1"],verdict="supported",reason="Direct source support.",evidence=[dict(source_id="S1",quote="Brew has two modes.")])],conflicts=[])


class SavedResearchTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/"data";root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.override=storage.database_override.set(str(Path(self.temp.name)/"research.db"))
        self.post=storage.save("post",dict(kind="post",brand_id="brand-test",platform="linkedin",status="approved",mode="live_mesh",brief="Brew features",
            text="Brew has two modes.",sources=[source("S1","Brew has two modes.")]))
    def tearDown(self):storage.database_override.reset(self.override);self.temp.cleanup()

    def test_evidence_followup_is_zero_call_and_reuses_snapshot(self):
        with patch.dict(os.environ,{"MESH_ENABLE_PAID":"0"}):
            turn=followups.answer(self.post,"Show sources","evidence","request1",mesh_factory=lambda:self.fail("No AI"))
        self.assertEqual(turn["ai_calls"],0);self.assertIn("Brew has two modes.",turn["text"])
        self.assertTrue(turn["source_snapshot_sha256"])

    def test_verified_conversation_reuses_history_and_is_idempotent(self):
        first=FollowupFake()
        with patch.dict(os.environ,{"MESH_ENABLE_PAID":"1"}):
            turn=followups.answer(self.post,"How many modes?","mesh","request1",lambda:first)
            repeat=followups.answer(self.post,"How many modes?","mesh","request1",lambda:self.fail("Repeat must not call AI"))
            second=FollowupFake();later=followups.answer(self.post,"Remind me of that feature","mesh","request2",lambda:second)
        self.assertEqual(turn["status"],"completed");self.assertEqual(first.call_count,2)
        self.assertEqual(repeat["id"],turn["id"]);self.assertTrue(second.contexts[0]["history"])
        self.assertEqual(later["source_snapshot_sha256"],turn["source_snapshot_sha256"])

    def test_paid_lock_and_no_source_path_do_not_spend(self):
        with patch.dict(os.environ,{"MESH_ENABLE_PAID":"0"}):
            with self.assertRaises(ValueError):followups.answer(self.post,"Question","mesh","request1")
        with patch.dict(os.environ,{"MESH_ENABLE_PAID":"1"}):
            turn=followups.answer(dict(self.post,sources=[]),"Question","mesh","request2",lambda:self.fail("No saved evidence"))
        self.assertEqual(turn["ai_calls"],0);self.assertEqual(turn["status"],"needs_evidence")

    def test_source_selection_never_hides_one_half_of_a_conflict(self):
        sources=[source(f"S{i}",f"Unrelated product evidence {i}.") for i in range(1,9)]
        sources.extend([source("S9","Brew has 2 modes."),source("S10","Brew has 3 modes.")])
        chosen,_=followups.snapshot(dict(self.post,sources=sources),"Brew modes")
        selected={s["source_id"] for s in chosen}
        self.assertLessEqual(len(chosen),8);self.assertTrue({"S9","S10"}<=selected or not selected&{"S9","S10"})

    def test_standalone_export_escapes_untrusted_text_and_exposes_conflicts(self):
        post=dict(self.post,brief='<script>alert(1)</script>',text='<img src=x onerror=alert(1)>',sources=[source("S1","Brew has 2 modes."),source("S2","Brew has 3 modes.")])
        html=render_report(post)
        self.assertNotIn('<script>',html);self.assertNotIn('<img src=',html)
        self.assertIn('&lt;script&gt;',html);self.assertIn('unresolved',html)
        self.assertIn('href="#source-S1"',html)

    def test_report_and_definition_endpoints_make_no_ai_calls(self):
        import main
        response=main.content_report(self.post["id"],download=True)
        self.assertIn("attachment",response.headers["content-disposition"])
        self.assertIn("default-src 'none'",response.headers["content-security-policy"])
        self.assertEqual(main.execution_definition(),definition())

    def test_followup_api_preserves_post_isolation_and_zero_call_mode(self):
        import main
        turn=main.content_followup(self.post["id"],main.FollowupRequest(question="Show evidence",mode="evidence",request_id="request1"))
        self.assertEqual(turn["ai_calls"],0)
        self.assertEqual(main.list_followups(self.post["id"])[0]["id"],turn["id"])
        other=storage.save("post",dict(kind="post",brand_id="other-brand",status="approved"))
        self.assertEqual(main.list_followups(other["id"]),[])

    def test_followup_call_budget_is_hard_bounded(self):
        mesh=Mesh.__new__(Mesh);mesh.metadata_only=False;mesh.call_count=0;mesh.image_count=0;mesh.max_calls=2
        with patch.dict(os.environ,{"MESH_MAX_CALLS":"10"}):
            mesh.reserve();mesh.reserve()
            with self.assertRaises(ValueError):mesh.reserve()


if __name__=="__main__":unittest.main()
