"""LangGraph incident-triage POC with a deterministic mock model by default."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langgraph.graph import END, START, StateGraph


RUNBOOKS = {
    "account_access": "RB-101: Check identity-provider status, collect affected-user count, and avoid account changes until an incident lead approves.",
    "payment_failure": "RB-204: Check payment-provider status, preserve transaction IDs, and do not retry customer charges automatically.",
    "data_exposure": "RB-301: Preserve evidence, restrict access, notify the security lead, and do not contact customers until legal review.",
    "service_outage": "RB-402: Check service health, establish an incident channel, and publish a status update after verification.",
    "general": "RB-001: Capture impact, timeline, owner, and next update time before closing the report.",
}


class IncidentState(TypedDict, total=False):
    incident: str
    category: str
    severity: str
    runbook: str
    draft_update: str
    status: str
    model_trace: list[str]
    approved: bool


class ChatModel:
    def classify(self, incident: str) -> str:
        raise NotImplementedError

    def draft(self, incident: str, category: str, severity: str, runbook: str) -> str:
        raise NotImplementedError


@dataclass
class MockChatModel(ChatModel):
    """Predictable fixture that makes every graph edge runnable without credentials."""

    def classify(self, incident: str) -> str:
        text = incident.lower()
        if any(term in text for term in ("leak", "exposed", "breach", "public bucket")):
            return "data_exposure"
        if any(term in text for term in ("login", "password", "sso", "account")):
            return "account_access"
        if any(term in text for term in ("payment", "charge", "checkout", "invoice")):
            return "payment_failure"
        if any(term in text for term in ("outage", "down", "unavailable", "500")):
            return "service_outage"
        return "general"

    def draft(self, incident: str, category: str, severity: str, runbook: str) -> str:
        return f"We are investigating a {severity} {category.replace('_', ' ')} incident. Next: follow {runbook.split(':')[0]} and provide a verified update within 30 minutes."


@dataclass
class HuggingFaceChatModel(ChatModel):
    token: str
    model: str = "openai/gpt-oss-120b:cheapest"

    def _complete(self, system: str, prompt: str) -> str:
        payload = json.dumps({"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0}).encode()
        request = Request("https://router.huggingface.co/v1/chat/completions", data=payload, headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())["choices"][0]["message"]["content"].strip()
        except (HTTPError, URLError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Hugging Face model call failed: {exc}") from exc

    def classify(self, incident: str) -> str:
        answer = self._complete("Classify incidents. Reply with one token only: account_access, payment_failure, data_exposure, service_outage, or general.", incident).lower().strip(" .`\n")
        return answer if answer in RUNBOOKS else "general"

    def draft(self, incident: str, category: str, severity: str, runbook: str) -> str:
        return self._complete("Draft a concise internal incident update. Do not claim a cause or remediation that is not in the incident or runbook.", f"Incident: {incident}\nCategory: {category}\nSeverity: {severity}\nRunbook: {runbook}")


def severity(incident: str, category: str) -> str:
    text = incident.lower()
    if category == "data_exposure" or any(term in text for term in ("all customers", "production down", "security", "sensitive")):
        return "critical"
    if any(term in text for term in ("multiple", "many users", "failed")):
        return "high"
    return "moderate"


def build_graph(model: ChatModel):
    def classify(state: IncidentState):
        category = model.classify(state["incident"])
        return {"category": category, "model_trace": state.get("model_trace", []) + ["classification model call"]}

    def assess(state: IncidentState):
        return {"severity": severity(state["incident"], state["category"])}

    def retrieve_runbook(state: IncidentState):
        return {"runbook": RUNBOOKS[state["category"]]}

    def draft_update(state: IncidentState):
        draft = model.draft(state["incident"], state["category"], state["severity"], state["runbook"])
        return {"draft_update": draft, "model_trace": state.get("model_trace", []) + ["drafting model call"]}

    def human_review(state: IncidentState):
        status = "approved_for_response" if state.get("approved") else "requires_human_review"
        return {"status": status}

    def finish(state: IncidentState):
        return {"status": "ready_for_response"}

    def route(state: IncidentState) -> Literal["human_review", "finish"]:
        return "human_review" if state["severity"] == "critical" else "finish"

    graph = StateGraph(IncidentState)
    graph.add_node("classify", classify)
    graph.add_node("assess", assess)
    graph.add_node("retrieve_runbook", retrieve_runbook)
    graph.add_node("draft_update", draft_update)
    graph.add_node("human_review", human_review)
    graph.add_node("finish", finish)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "assess")
    graph.add_edge("assess", "retrieve_runbook")
    graph.add_edge("retrieve_runbook", "draft_update")
    graph.add_conditional_edges("draft_update", route)
    graph.add_edge("human_review", END)
    graph.add_edge("finish", END)
    return graph.compile()


def choose_model(provider: str) -> ChatModel:
    if provider == "mock":
        return MockChatModel()
    token = os.getenv("HF_TOKEN")
    if not token:
        raise ValueError("Set HF_TOKEN before using the Hugging Face provider.")
    return HuggingFaceChatModel(token, os.getenv("HF_MODEL", "openai/gpt-oss-120b:cheapest"))


def run(incident: str, provider="mock", approved=False):
    return build_graph(choose_model(provider)).invoke({"incident": incident, "approved": approved})
