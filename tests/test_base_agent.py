"""BaseToolAgent loop with fake Qwen client."""
from __future__ import annotations

import json

from emergencynet.base_agent import BaseToolAgent
from emergencynet.gateway import BaseGateway
from emergencynet.meshtastic_broadcaster import MeshAlertBroadcaster
from emergencynet.qwen_client import QwenResponse


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.i = 0

    def chat(self, messages, **kwargs):
        if self.i >= len(self.responses):
            return QwenResponse(content="done")
        r = self.responses[self.i]
        self.i += 1
        return r


def test_agent_direct_answer():
    gw = BaseGateway()
    client = FakeClient([QwenResponse(content="All quiet.")])
    agent = BaseToolAgent(gateway=gw, client=client, max_steps=3)
    out = agent.run("Status?")
    assert out["ok"]
    assert "quiet" in out["text"].lower()


def test_agent_draft_tool_then_final():
    gw = BaseGateway()
    tool_resp = QwenResponse(
        content="",
        tool_calls=[{
            "id": "c1",
            "type": "function",
            "function": {
                "name": "draft_mesh_alert",
                "arguments": json.dumps({
                    "severity": "critical",
                    "anomaly_type": "RED_SURGE",
                    "message_body": "Activate MCM",
                }),
            },
        }],
    )
    final = QwenResponse(content="Draft ready for approval.")
    agent = BaseToolAgent(gateway=gw, client=FakeClient([tool_resp, final]), max_steps=4)
    out = agent.run("Draft alert for RED surge")
    assert out["ok"]
    assert agent.drafts()
    assert any(d["message_body"] == "Activate MCM" for d in agent.drafts().values())


def test_send_blocked_without_human():
    gw = BaseGateway()
    sent = []
    b = MeshAlertBroadcaster(transport_send_text=lambda t: sent.append(t) or True)
    agent = BaseToolAgent(gateway=gw, broadcaster=b, client=FakeClient([]))
    d = agent._tool_draft_mesh_alert(
        severity="high", anomaly_type="BURN_CLUSTER", message_body="Fire cluster",
    )
    blocked = agent._tool_request_send_broadcast(
        draft_id=d["draft_id"], human_approved=False,
    )
    assert blocked["sent"] is False
    assert blocked["error"] == "human_approval_required"
    assert not sent
    ok = agent._tool_request_send_broadcast(
        draft_id=d["draft_id"], human_approved=True,
    )
    assert ok["sent"] is True
    assert sent


def test_model_cannot_fabricate_human_approval():
    """A model-supplied true must be overwritten inside the agent dispatcher."""
    gw = BaseGateway()
    sent = []
    b = MeshAlertBroadcaster(transport_send_text=lambda t: sent.append(t) or True)
    agent = BaseToolAgent(gateway=gw, broadcaster=b, client=FakeClient([]))
    d = agent._tool_draft_mesh_alert(
        severity="critical", anomaly_type="RED_SURGE", message_body="Activate MCM",
    )

    result = agent._dispatch_tool("request_send_broadcast", {
        "draft_id": d["draft_id"],
        "human_approved": True,
    })

    assert result["sent"] is False
    assert result["error"] == "human_approval_required"
    assert not sent
