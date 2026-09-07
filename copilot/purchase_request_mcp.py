"""A deliberately small, read-only MCP server for local development.

It exposes request context to an MCP client over stdio.  It has no tools for
approval, ordering, or editing: those actions stay behind the application's
role checks and browser/API flows.
"""
import json
import sys

from .purchase_request_workflow import Principal, Workflow


TOOLS = [
    {
        "name": "list_purchase_requests",
        "description": "List purchase requests visible to the configured local principal.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_purchase_request",
        "description": "Get a request, review packet, and audit timeline by request ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"request_id": {"type": "string"}},
            "required": ["request_id"],
        },
    },
]


def tool_result(workflow, principal, name, arguments):
    if name == "list_purchase_requests":
        data = workflow.list(principal)
    elif name == "get_purchase_request":
        rid = arguments.get("request_id")
        if not isinstance(rid, str):
            raise ValueError("request_id must be a string.")
        data = workflow.get(rid, principal)
        data["audit"] = workflow.audit_history(rid, principal)
    else:
        raise ValueError(f"Unknown tool: {name}")
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2, default=str)}]}


def run(database, principal):
    workflow = Workflow(database)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                method = request.get("method")
                if method == "initialize":
                    result = {
                        "protocolVersion": request.get("params", {}).get("protocolVersion", "2025-03-26"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "purchase-request-copilot", "version": "0.1.0"},
                    }
                elif method == "tools/list":
                    result = {"tools": TOOLS}
                elif method == "tools/call":
                    params = request.get("params", {})
                    result = tool_result(workflow, principal, params.get("name"), params.get("arguments", {}))
                else:
                    raise ValueError(f"Unsupported method: {method}")
                response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            except Exception as exc:
                response = {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32000, "message": str(exc)}}
            print(json.dumps(response), flush=True)
    finally:
        workflow.close()
