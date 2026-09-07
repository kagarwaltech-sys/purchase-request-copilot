# Features and walkthroughs

This repository contains two independent agentic demonstrations. Both are
local-first, use synthetic data, and keep business decisions in deterministic
application code.

## Purchase Request Copilot

The Purchase Request Copilot turns a software purchase request into a reviewed,
version-bound approval and a mock order.

| Capability | What it demonstrates |
| --- | --- |
| Request form and inbox | Create and track software-purchase requests in the browser |
| Role fixtures | Alice is a requester, Bob is a design approver, and Eve is an engineering approver |
| Specialized review | Intake, policy, and vendor-risk agents produce a typed review packet |
| Deterministic gates | Required fields, annual cost, vendor attestation, ownership, department, and approval version are enforced in code |
| Audit timeline | Shows creation, review, edits, approval, and mock-order events |
| JSON API | Supports programmatic create, read, update, review, approve, and order operations |
| Read-only MCP tools | Lets an MCP client list or inspect a visible request without authority to change it |

### Browser walkthrough

1. Run `python -m copilot serve --db demo.sqlite3` and open the displayed URL.
2. Sign in as **Alice** and create a request. Choose `Not yet known` for
   customer data to see the missing-information path.
3. Complete the answer and run the review. The review result presents a plain
   language decision, each agent's finding, cited evidence labels, and raw data.
4. Sign out and sign in as **Bob** to approve an eligible request.
5. Sign back in as **Alice** to submit its idempotent mock order.
6. Edit a request after approval to see the version increment and approval
   invalidation.

Try `RiskyCloud` with customer data to see an attestation blocker, or
`InjectedVendor` with customer data to see untrusted instruction-like vendor
text treated as evidence rather than a command.

## Incident Triage Copilot

The Incident Triage Copilot is a LangGraph workflow for preparing an internal
incident response from a short report.

| Graph step | Responsibility |
| --- | --- |
| Classify | A model call categorizes the report as account access, payment failure, data exposure, service outage, or general |
| Assess | Deterministic rules assign `moderate`, `high`, or `critical` severity |
| Retrieve runbook | Selects a versioned, category-specific response guide |
| Draft | A second model call produces a candidate; it is never shown directly |
| Constrain update | Builds the operator-facing update from verified state and runbook text only |
| Route | Critical incidents require human review; other incidents are ready for a response |

Run it with the built-in deterministic model:

```powershell
python -m copilot incident --incident "A public bucket may have exposed customer records."
```

Use `--approved` to simulate the human decision after a critical incident has
been reviewed. The optional Hugging Face provider is described in the root
README.

## Verification

```powershell
python -m unittest discover -s tests -v
```

The tests cover workflow permissions, approval invalidation, request isolation,
idempotent ordering, MCP read scoping, LangGraph routing, local environment
loading, and removal of deliberately fabricated model details.
