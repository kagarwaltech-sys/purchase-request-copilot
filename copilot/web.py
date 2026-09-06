"""Small local web UI for the mock purchase workflow.

This module deliberately uses only the standard library so the POC remains
immediately runnable.  Its fixed identities are demonstration fixtures, not
authentication.
"""
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from urllib.parse import parse_qs, quote, urlparse

from .core import INVENTORY, VENDORS, Principal, Workflow


STYLE = """
body{font:16px system-ui,sans-serif;max-width:1040px;margin:32px auto;padding:0 20px;color:#1d2939;background:#f8fafc}
h1{margin-bottom:4px} .muted{color:#667085} header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}.card{background:#fff;border:1px solid #d0d5dd;border-radius:10px;padding:18px;margin:18px 0}
label{display:block;font-weight:600;margin:10px 0 4px} input,select,button{font:inherit;padding:8px;border:1px solid #98a2b3;border-radius:6px} input,select{width:100%;box-sizing:border-box}button{width:auto;background:#155eef;color:#fff;border:0;cursor:pointer;margin-top:14px}button.secondary{background:#475467}
.flash{padding:12px;border-radius:8px;background:#fef0c7;color:#7a2e0e}.success{padding:12px;border-radius:8px;background:#dcfae6;color:#05603a}.state{display:inline-block;padding:3px 8px;border-radius:99px;background:#e0eaff;font-size:13px;font-weight:700}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #eaecf0}code{overflow-wrap:anywhere}details{margin-top:12px}pre{white-space:pre-wrap;word-break:break-word;background:#f2f4f7;padding:12px;border-radius:6px}.agents{display:grid;gap:8px}.agent{padding:12px;border:1px solid #d0d5dd;border-radius:8px}.agent h3{margin:0 0 6px}.agent p{margin:6px 0}
"""


def actor(role):
    return Principal("bob", "design", "approver") if role == "approver" else Principal("alice", "design")


def page(title, content, message=""):
    alert = f'<p class="flash">{escape(message)}</p>' if message else ""
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{escape(title)}</title><style>{STYLE}</style></head>
    <body><header><div><h1>Purchase Request Copilot</h1><p class=muted>Local interactive mock workflow</p></div><a href='/'>Request inbox</a></header>{alert}{content}</body></html>"""


def request_form():
    vendors = "".join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in VENDORS)
    return f"""<section class=card><h2>New purchase request</h2><form method=post action=/create>
    <label>Vendor</label><select name=vendor>{vendors}</select><label>Seats</label><input name=seats type=number min=1 value=12 required>
    <label>Monthly price per seat (USD)</label><input name=monthly_price type=number min=0.01 step=0.01 value=25.00 required>
    <label>Will customer data be shared?</label><select name=customer_data><option value=false>No</option><option value=true>Yes</option><option value=unknown>Not yet known</option></select>
    <button>Create request</button></form></section>"""


def review_packet(packet):
    """Render a readable decision view while keeping the raw packet available."""
    if not packet:
        return "<p>No review has run yet. Use <b>Run review</b> when the request is ready.</p>"
    if packet["missing"]:
        items = "".join(f"<li>{escape(field.replace('_', ' ').title())}</li>" for field in packet["missing"])
        decision = f"<p class=flash>More information is needed before this request can be reviewed.</p><p>Please complete:</p><ul>{items}</ul>"
    elif packet["blockers"]:
        items = "".join(f"<li>{escape(reason)}</li>" for reason in packet["blockers"])
        decision = f"<p class=flash>This request cannot proceed under the demo policy.</p><p>Reason:</p><ul>{items}</ul>"
    else:
        decision = "<p class=success>This request passed the automated checks and is ready for Bob’s approval.</p>"
    findings = "".join(
        f"<article class=agent><h3>{escape(finding['agent'].title())} agent</h3>"
        f"<p>{escape(finding['summary'])}</p><p class=muted>Route: {escape(finding['route'])}<br>"
        f"Evidence: {escape(', '.join(finding['evidence']))}</p></article>"
        for finding in packet["findings"]
    )
    raw = escape(json.dumps(packet, indent=2))
    return f"""<p><b>Annual cost:</b> ${escape(packet['annual_cost'])}</p>{decision}
    <h3>Agents that worked on this request</h3><div class=agents>{findings}</div>
    <details><summary>View raw review packet</summary><pre>{raw}</pre></details>"""


def inbox(workflow, message=""):
    rows = workflow.list(actor("requester"))
    table = "".join(f"<tr><td><a href='/request?id={escape(r['id'])}'><code>{escape(r['id'][:12])}</code></a></td><td>{escape(r['body']['vendor'])}</td><td><span class=state>{escape(r['state'])}</span></td><td>{r['version']}</td></tr>" for r in rows)
    content = request_form() + f"<section class=card><h2>Design department inbox</h2><table><tr><th>Request</th><th>Vendor</th><th>State</th><th>Version</th></tr>{table or '<tr><td colspan=4>No requests yet.</td></tr>'}</table></section>"
    return page("Purchase Request Copilot", content, message)


def details(workflow, rid, message=""):
    requester = actor("requester")
    item = workflow.get(rid, requester)
    body = item["body"]
    can_edit = item["state"] != "ordered"
    actions = ""
    if can_edit:
        actions += f"""<form method=post action=/update><input type=hidden name=id value={escape(rid)}><label>Seats</label><input name=seats type=number min=1 value={body['seats']} required><label>Monthly price</label><input name=monthly_price type=number min=.01 step=.01 value={escape(body['monthly_price'])} required><label>Customer data</label><select name=customer_data><option value=false {'selected' if body['customer_data'] is False else ''}>No</option><option value=true {'selected' if body['customer_data'] is True else ''}>Yes</option><option value=unknown {'selected' if body['customer_data'] is None else ''}>Not yet known</option></select><button class=secondary>Save changes</button></form><form method=post action=/review><input type=hidden name=id value={escape(rid)}><button>Run review</button></form>"""
    if item["state"] == "awaiting_approval":
        actions += f"<form method=post action=/approve><input type=hidden name=id value={escape(rid)}><input type=hidden name=version value={item['version']}><button>Approve as Bob</button></form>"
    if item["state"] in ("approved", "ordered"):
        actions += f"<form method=post action=/order><input type=hidden name=id value={escape(rid)}><button>Submit mock order</button></form>"
    packet = review_packet(item["packet"])
    content = f"""<p><a href='/'>← Inbox</a></p><section class=card><h2>{escape(body['vendor'])} <span class=state>{escape(item['state'])}</span></h2><p><b>Request ID:</b> <code>{escape(rid)}</code><br><b>Version:</b> {item['version']}<br><b>Seats:</b> {body['seats']}<br><b>Monthly price:</b> ${escape(body['monthly_price'])}<br><b>Customer data:</b> {escape(str(body['customer_data']))}</p></section><section class='card grid'><div><h2>Actions</h2>{actions or '<p>This request is complete.</p>'}</div><div><h2>Review results</h2>{packet}</div></section>"""
    return page("Request details", content, message)


class App(BaseHTTPRequestHandler):
    workflow = None

    def log_message(self, format, *args):
        return

    def respond(self, content, status=200):
        encoded = content.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self.respond(inbox(self.workflow, query.get("message", [""])[0]))
            elif parsed.path == "/request" and query.get("id"):
                self.respond(details(self.workflow, query["id"][0], query.get("message", [""])[0]))
            else:
                self.respond(page("Not found", "<h2>Page not found</h2>"), 404)
        except (ValueError, PermissionError) as exc:
            self.respond(page("Request unavailable", f"<h2>Request unavailable</h2><p>{escape(str(exc))}</p>"), 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = {key: values[-1] for key, values in parse_qs(self.rfile.read(length).decode()).items()}
        rid = data.get("id")
        try:
            if self.path == "/create":
                flag = {"true": True, "false": False, "unknown": None}[data["customer_data"]]
                rid = self.workflow.create(actor("requester"), data["vendor"], int(data["seats"]), data["monthly_price"], flag)
                message = "Request created. Add any missing information, then run the review."
            elif self.path == "/update":
                flag = {"true": True, "false": False, "unknown": None}[data["customer_data"]]
                self.workflow.update(rid, actor("requester"), seats=int(data["seats"]), monthly_price=data["monthly_price"], customer_data=flag)
                message = "Request updated; its prior review and approval were cleared."
            elif self.path == "/review":
                self.workflow.review(rid, actor("requester"))
                message = "Review completed."
            elif self.path == "/approve":
                self.workflow.approve(rid, actor("approver"), int(data["version"]))
                message = "Approved by Bob for this exact request version."
            elif self.path == "/order":
                order = self.workflow.order(rid, actor("requester"))
                message = f"Mock order submitted: {order}"
            else:
                raise ValueError("Unknown action.")
        except (KeyError, ValueError, PermissionError) as exc:
            message = str(exc)
        self.send_response(303)
        self.send_header("Location", f"/request?id={quote(rid or '')}&message={quote(message)}")
        self.end_headers()


def serve(host="127.0.0.1", port=8000, database=":memory:"):
    App.workflow = Workflow(database)
    server = HTTPServer((host, port), App)
    print(f"Purchase Request Copilot is running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
        App.workflow.close()
