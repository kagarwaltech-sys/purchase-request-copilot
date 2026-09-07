import argparse
import json
from .core import Principal, Workflow
from .incident import run as run_incident
from .mcp_server import run as run_mcp
from .web import serve


def main():
    parser = argparse.ArgumentParser(description="Purchase Request Copilot mock demonstration")
    parser.add_argument("command", choices=["demo", "serve", "mcp", "incident"])
    parser.add_argument("--db", default=":memory:")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--user", choices=["alice", "bob", "eve"], default="alice")
    parser.add_argument("--incident", default="Multiple users cannot log in after an SSO configuration change.")
    parser.add_argument("--provider", choices=["mock", "huggingface"], default="mock")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    if args.command == "serve":
        serve(host=args.host, port=args.port, database=args.db)
        return
    if args.command == "mcp":
        principals = {
            "alice": Principal("alice", "design"),
            "bob": Principal("bob", "design", "approver"),
            "eve": Principal("eve", "engineering", "approver"),
        }
        run_mcp(args.db, principals[args.user])
        return
    if args.command == "incident":
        print(json.dumps(run_incident(args.incident, args.provider, args.approved), indent=2))
        return
    workflow = Workflow(args.db)
    employee = Principal("alice", "design")
    approver = Principal("bob", "design", "approver")
    try:
        normal = workflow.create(employee)
        workflow.review(normal, employee)
        workflow.approve(normal, approver, expected_version=1)
        order = workflow.order(normal, employee)
        print(f"Normal: ordered ({order}); retry returns same order: {workflow.order(normal, employee) == order}")

        missing = workflow.create(employee, customer_data=None)
        result = workflow.review(missing, employee)
        print(f"Missing information: {result['state']} - {result['packet']['missing']}")

        malicious = workflow.create(employee, vendor="InjectedVendor", customer_data=True)
        result = workflow.review(malicious, employee)
        print(f"Malicious document: {result['state']}")
        print(json.dumps(result["packet"], indent=2))

        changed = workflow.create(employee)
        workflow.review(changed, employee)
        workflow.approve(changed, approver, expected_version=1)
        workflow.update(changed, employee, seats=15)
        try:
            workflow.order(changed, employee)
        except ValueError as exc:
            print(f"Changed after approval: order rejected - {exc}")
        print("All agents are simulated; no external services or models were called.")
    finally:
        workflow.close()


if __name__ == "__main__":
    main()
