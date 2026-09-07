# Purchase Request Copilot

A portfolio POC for embedding specialized AI agents into a controlled purchasing workflow.

It also contains an independent **Incident Triage Copilot** built with
LangGraph. That POC classifies an incident, applies deterministic severity
rules, retrieves a runbook, drafts an internal update, and routes critical
incidents to human review.

Read [features and walkthroughs](docs/features.md), the [architecture guide](docs/architecture.md),
and the detailed [design rationale](docs/design.md) for an overview before
running either demo.

## Two independent implementations

| Implementation | Location | Purpose | Run command |
| --- | --- | --- | --- |
| Deterministic Purchase Request Copilot | `copilot/core.py` | Controlled purchase workflow with specialized mock agents, UI, API, SQLite, and MCP read tools | `python -m copilot demo` or `python -m copilot serve` |
| LangGraph Incident Triage Copilot | `copilot/incident.py` | Stateful incident triage graph with model calls, deterministic policy, runbooks, and human-review routing | `python -m copilot incident` |

The LangGraph work did not replace the purchase implementation. The purchase
commands import no LangGraph code, so they remain runnable without installing
the incident POC dependency.

## Run

The purchase workflow requires Python 3.11+ and no packages or credentials.
The incident workflow additionally requires LangGraph, as shown below.

```powershell
cd C:\Users\16122\learn\purchase-request-copilot
python -m copilot demo
python -m copilot incident
python -m unittest discover -s tests -v
```

## Incident Triage Copilot

Install LangGraph before running this POC outside Docker:

```powershell
python -m pip install -r requirements.txt
python -m copilot incident --incident "A public bucket may have exposed customer records."
```

The default `mock` provider makes two predictable model-shaped calls and needs
no key. Critical incidents end in `requires_human_review`; pass `--approved`
to record a simulated human approval after reviewing the draft.

For a credible live demonstration, use Hugging Face Inference Providers. Its
free tier supplies monthly inference credits, and its chat-completions endpoint
is OpenAI-compatible. Create a fine-grained token with the “Make calls to
Inference Providers” permission, then set `HF_TOKEN` in PowerShell for the
current shell. Alternatively, paste the value after `HF_TOKEN=` in the local
`.env` file; it is ignored by Git and loaded automatically:

```powershell
$env:HF_TOKEN = "hf_your_token"
python -m copilot incident --provider huggingface --incident "Payment checkout is failing for many users."
```

The adapter calls `https://router.huggingface.co/v1/chat/completions` and
defaults to `openai/gpt-oss-120b:cheapest`; change `HF_MODEL` if needed. Keep
`mock` for repeatable tests and use the live provider only with synthetic text.
Model prose is treated as untrusted: the operator-facing update is constructed
only from verified graph state and the selected runbook, preventing invented
incident IDs, timestamps, completed actions, causes, or impact claims.
See the [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
and [Hugging Face Inference Providers documentation](https://huggingface.co/docs/inference-providers/en/index)
for current details.

## Interactive UI

Start the local UI, then open the printed address in a browser:

```powershell
python -m copilot serve
```

The UI uses fixed local demo identities: Alice creates, edits, reviews, and
orders requests; Bob approves eligible requests. It is a development demo and
uses local in-memory demo sessions rather than production authentication. Use
`--db demo.sqlite3` to keep requests after the server stops, or `--port 8080`
to choose a different port.

The UI includes an audit timeline, readable agent findings, and role-aware
actions. Sign in as Alice to create, edit, review, and order; sign in as Bob to
review the design inbox and approve eligible requests. Eve demonstrates that a
different department cannot access design requests.

## Local API

After signing in through the UI, the browser session can call the local JSON
API. The API enforces the same role and department checks as the UI:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/requests` | List visible requests |
| `POST` | `/api/requests` | Create a request |
| `GET` | `/api/requests/{id}` | Request, review packet, and audit timeline |
| `PATCH` | `/api/requests/{id}` | Update a requester-owned request |
| `POST` | `/api/requests/{id}/review` | Run review |
| `POST` | `/api/requests/{id}/approve` | Approve with `expected_version` |
| `POST` | `/api/requests/{id}/order` | Create the mock order |

The API is intentionally local-only until a real identity provider, CSRF
protection, TLS, and production session storage are added.

## MCP integration

The optional MCP server exposes two read-only tools: `list_purchase_requests`
and `get_purchase_request`. It intentionally cannot edit, approve, or order.
Run it against a persistent local database:

```powershell
python -m copilot mcp --db demo.sqlite3 --user alice
```

For an MCP client that accepts a stdio configuration, use this shape (replace
the path if the project is elsewhere):

```json
{
  "mcpServers": {
    "purchase-request-copilot": {
      "command": "python",
      "args": ["-m", "copilot", "mcp", "--db", "demo.sqlite3", "--user", "alice"]
    }
  }
}
```

Configure the MCP client with this project as its working directory so it can
resolve `copilot` and `demo.sqlite3`.

## Docker Compose

Install and start Docker Desktop, then run the application from this project
directory:

```powershell
docker compose config
docker compose up --build
```

Open http://localhost:8000. Compose stores the local SQLite database in its
`purchase_request_data` volume, so requests remain available after restarting
the app. Stop the server with `Ctrl+C`.

### Run the Incident Triage Copilot in Docker

The Docker image includes LangGraph and the Incident Triage Copilot. Run its
deterministic mock provider without credentials:

```powershell
docker compose run --rm app python -m copilot incident
```

To run the live Hugging Face provider, pass the token from the current
PowerShell session into the one-off container:

```powershell
docker compose run --rm -e HF_TOKEN=$env:HF_TOKEN app python -m copilot incident --provider huggingface
```

The local `.env` file is intentionally excluded from the image and is not sent
to Docker. This keeps the token out of the build context; set `HF_TOKEN` in the
shell first or pass its value with `-e` as shown above.

Run the test suite in the same image:

```powershell
docker compose --profile test run --rm test
```

To remove the app and its saved local demo data:

```powershell
docker compose down --volumes
```

The demo uses an in-memory database by default. To retain its request records:

```powershell
python -m copilot demo --db demo.sqlite3
```

Each run creates fresh requests. Output demonstrates normal approval, missing information, an injected vendor instruction, and invalidation of approval after a request changes.

## Current implementation

- Three deterministic agent simulators with typed outputs and restricted input contexts.
- Parallel policy/vendor reviews, explicit workflow states, version-bound approval.
- SQLite request and audit persistence; atomic, idempotent mock order creation.
- Department-scoped access and separate requester/approver roles.
- Versioned policy fixtures, evidence references, mock vendor and inventory services.
- Security and workflow regression tests.

This is an executable workflow foundation, not a live LLM integration. Model routing is recorded as a proposed route; no model is invoked. CLI identities are test fixtures, not authentication. The local database is not encrypted and audit records are not tamper-proof. Use synthetic data only.

Read [the design](docs/design.md) for architecture, controls, memory strategy, evaluations, and the implementation roadmap.

The [synthetic evidence catalog](docs/mock-evidence.md) explains the policy and vendor references in review packets.
