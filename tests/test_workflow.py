from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from copilot.core import Principal, Workflow
from copilot.mcp_server import tool_result
from copilot.incident import load_local_env, run as run_incident


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.w = Workflow()
        self.employee = Principal("alice", "design")
        self.approver = Principal("bob", "design", "approver")

    def tearDown(self):
        self.w.close()

    def ready(self, **kwargs):
        rid = self.w.create(self.employee, **kwargs)
        self.w.review(rid, self.employee)
        return rid

    def test_order_requires_approval_and_is_idempotent(self):
        rid = self.ready()
        with self.assertRaises(ValueError):
            self.w.order(rid, self.employee)
        self.w.approve(rid, self.approver, 1)
        self.assertEqual(self.w.order(rid, self.employee), self.w.order(rid, self.employee))
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM orders").fetchone()[0], 1)
        with self.assertRaises(PermissionError):
            self.w.update(rid, self.employee, seats=3)

    def test_missing_answer_can_be_completed(self):
        rid = self.ready(customer_data=None)
        self.assertEqual(self.w.get(rid, self.employee)["state"], "needs_information")
        with self.assertRaises(ValueError):
            self.w.approve(rid, self.approver, 1)
        self.w.update(rid, self.employee, customer_data=False)
        self.assertEqual(self.w.review(rid, self.employee)["state"], "awaiting_approval")

    def test_injected_document_cannot_authorize_purchase(self):
        rid = self.ready(vendor="InjectedVendor", customer_data=True)
        self.assertEqual(self.w.get(rid, self.employee)["state"], "blocked")
        with self.assertRaises(ValueError):
            self.w.approve(rid, self.approver, 1)
        with self.assertRaises(ValueError):
            self.w.order(rid, self.employee)

    def test_update_clears_approval_and_stale_version_is_rejected(self):
        rid = self.ready()
        self.w.approve(rid, self.approver, 1)
        self.w.update(rid, self.employee, seats=15)
        self.assertIsNone(self.w.get(rid, self.employee)["approved_version"])
        with self.assertRaises(ValueError):
            self.w.order(rid, self.employee)
        self.w.review(rid, self.employee)
        with self.assertRaises(ValueError):
            self.w.approve(rid, self.approver, 1)
        self.w.approve(rid, self.approver, 2)
        self.w.order(rid, self.employee)

    def test_department_scope_applies_to_reads_and_mutations(self):
        rid = self.ready()
        outsider = Principal("eve", "engineering", "approver")
        for action in (lambda: self.w.get(rid, outsider),
                       lambda: self.w.approve(rid, outsider, 1),
                       lambda: self.w.update(rid, outsider, seats=1),
                       lambda: self.w.review(rid, outsider),
                       lambda: self.w.order(rid, outsider)):
            with self.assertRaises(PermissionError):
                action()

    def test_department_inbox_is_scoped(self):
        rid = self.w.create(self.employee)
        self.assertEqual([item["id"] for item in self.w.list(self.employee)], [rid])
        self.assertEqual(self.w.list(Principal("eve", "engineering")), [])

    def test_audit_history_is_scoped_and_ordered(self):
        rid = self.w.create(self.employee)
        self.w.review(rid, self.employee)
        history = self.w.audit_history(rid, self.employee)
        self.assertEqual([event["event"] for event in history], ["created", "reviewed"])
        with self.assertRaises(PermissionError):
            self.w.audit_history(rid, Principal("eve", "engineering"))

    def test_mcp_tools_are_read_only_and_scoped(self):
        rid = self.w.create(self.employee)
        result = tool_result(self.w, self.employee, "get_purchase_request", {"request_id": rid})
        self.assertIn(rid, result["content"][0]["text"])
        with self.assertRaises(PermissionError):
            tool_result(self.w, Principal("eve", "engineering"), "get_purchase_request", {"request_id": rid})

    def test_incident_graph_routes_critical_cases_to_human_review(self):
        result = run_incident("A public bucket exposed customer records.")
        self.assertEqual(result["category"], "data_exposure")
        self.assertEqual(result["severity"], "critical")
        self.assertEqual(result["status"], "requires_human_review")
        self.assertEqual(len(result["model_trace"]), 2)

    def test_incident_graph_can_finish_noncritical_case(self):
        result = run_incident("One employee cannot log in to the dashboard.")
        self.assertEqual(result["status"], "ready_for_response")

    def test_local_env_loads_model_settings_without_overwriting_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("HF_TOKEN=local-token\nHF_MODEL=example/model\n")
            with patch.dict("os.environ", {"HF_TOKEN": "shell-token"}, clear=True):
                load_local_env(env_file)
                self.assertEqual(os.environ["HF_TOKEN"], "shell-token")
                self.assertEqual(os.environ["HF_MODEL"], "example/model")

    def test_requester_cannot_approve_even_with_approver_role(self):
        rid = self.ready()
        for actor in (self.employee, Principal("alice", "design", "approver")):
            with self.assertRaises(PermissionError):
                self.w.approve(rid, actor, 1)

    def test_budget_and_numeric_validation(self):
        rid = self.ready(seats=100)
        self.assertEqual(self.w.get(rid, self.employee)["state"], "blocked")
        for price in ("NaN", "Infinity", "-1", "1.001", "invalid"):
            with self.assertRaises(ValueError):
                self.w.create(self.employee, monthly_price=price)
        with self.assertRaises(ValueError):
            self.w.create(self.employee, seats=True)

    def test_approved_request_cannot_be_rereviewed(self):
        rid = self.ready()
        self.w.approve(rid, self.approver, 1)
        with self.assertRaises(ValueError):
            self.w.review(rid, self.employee)

    def test_approval_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "workflow.sqlite3")
            first = Workflow(path)
            try:
                rid = first.create(self.employee)
                first.review(rid, self.employee)
                first.approve(rid, self.approver, 1)
            finally:
                first.close()
            second = Workflow(path)
            try:
                self.assertTrue(second.order(rid, self.employee).startswith("MOCK-"))
                self.assertEqual(second.db.execute("SELECT count(*) FROM audit").fetchone()[0], 4)
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
