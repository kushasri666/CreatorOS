"""Small compiled state-graph framework with validated routes and bounded execution."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    name: str
    responsibility: str
    successors: tuple


NODES = (
    Node("research", "Retrieve product documents, official pages and scoped observations", ("source_review",)),
    Node("source_review", "Weight source provenance and flag cross-source conflicts", ("strategist", "writer_correction")),
    Node("strategist", "Choose a product-specific angle and audience", ("writer",)),
    Node("writer", "Draft or revise against editorial feedback", ("editor", "verifier")),
    Node("editor", "Score concrete criteria and route refinement or re-planning", ("writer", "strategist", "verifier")),
    Node("verifier", "Check claims, quotations and disagreements across sources", ("research_retry", "editor_recheck", "quality_gate")),
    Node("research_retry", "Gather additional evidence once after verification failure", ("source_review", "quality_gate")),
    Node("writer_correction", "Remove or qualify unsupported and disputed claims", ("verifier", "quality_gate")),
    Node("editor_recheck", "Re-score the verifier-corrected content", ("quality_gate",)),
    Node("quality_gate", "Require editorial and evidence approval", ("visual", "finish")),
    Node("visual", "Prepare matching imagery within the remaining Mesh budget", ("finish",)),
    Node("finish", "Return the persisted, auditable content state", ()),
)


def definition():
    return dict(framework="CreatorOS StateGraph", entry="research", terminal="finish", max_steps=48,
        nodes=[dict(name=n.name,responsibility=n.responsibility,successors=list(n.successors)) for n in NODES],
        retry_limit=1, note="This definition drives execution; graph steps do not themselves call a model.")


class StateGraph:
    def __init__(self, handlers, record):
        self.nodes={n.name:n for n in NODES}
        if set(handlers)!=set(self.nodes):raise ValueError("Every declared graph node needs exactly one handler")
        if any(to not in self.nodes for n in NODES for to in n.successors):raise ValueError("Unknown graph successor")
        self.handlers=handlers;self.record=record

    def run(self, state):
        current="research";trace=[]
        for step in range(48):
            self.record("graph_node",dict(node=current,step=step+1,reason=self.nodes[current].responsibility))
            following=self.handlers[current](state)
            trace.append(dict(step=step+1,node=current,next=following))
            if current=="finish":
                if following is not None:raise ValueError("Terminal node cannot route onward")
                return trace
            if following not in self.nodes[current].successors:
                raise ValueError(f"Invalid graph edge {current} -> {following}")
            self.record("graph_transition",dict(from_node=current,to_node=following,step=step+1,
                reason="Handler selected this declared state-graph edge."))
            current=following
        raise ValueError("State graph exceeded its bounded execution limit")
