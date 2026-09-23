"""Small localhost-only review form; no login or authenticated identity."""

from __future__ import annotations

import html
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .acceptance_ledger import append_event, context, evaluate


def _h(value: object) -> str:
    return html.escape(str(value), quote=True)


def serve(config_path: Path, events_path: Path, port: int = 8765) -> None:
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    config_path, events_path = Path(config_path), Path(events_path)
    token = secrets.token_urlsafe(32)

    class ReviewHandler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: str) -> None:
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def _page(self, content: str) -> str:
            return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Acceptance Ledger</title>"
                    "<style>body{font:16px system-ui;background:#0b1220;color:#f9fafb;max-width:1100px;margin:auto;padding:28px}"
                    "a{color:#67e8f9}table{border-collapse:collapse;width:100%}td,th{border:1px solid #64748b;padding:9px;text-align:left}"
                    "input,select,textarea{background:#111827;color:#fff;border:1px solid #94a3b8;padding:8px;width:100%;box-sizing:border-box}"
                    "button{background:#155e75;color:white;border:2px solid #67e8f9;padding:10px 18px;cursor:pointer}"
                    ".table-wrap{overflow-x:auto}.ok{border:2px solid #4ade80;padding:10px;background:#123323}"
                    ".warn{border:2px solid #fbbf24;padding:12px;background:#3b2f15}label{display:block;margin:12px 0}</style>"
                    "<h1>Acceptance Ledger</h1><p class='warn'>Local reference only. Reviewer aliases and timestamps are not authenticated."
                    " Do not enter private customer data in this public demo.</p>" + content + "</html>")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in ("/", "/task"):
                self._send(404, self._page("<p>Not found.</p>"))
                return
            try:
                ctx = context(config_path)
                passport = evaluate(config_path, events_path)
                rows = {row["task_id"]: row for row in passport["task_results"]}
                links = "<ul>" + "".join(f"<li><a href='/task?task_id={quote(task_id)}'>{_h(task_id)}</a> — {_h(rows[task_id]['outcome'])}</li>" for task_id in sorted(ctx["tasks"])) + "</ul>"
                if parsed.path == "/":
                    self._send(200, self._page("<p>Select a public filing task for blind review.</p>" + links))
                    return
                task_id = parse_qs(parsed.query).get("task_id", [""])[0]
                if task_id not in ctx["tasks"]:
                    self._send(404, self._page("<p>Unknown task.</p>"))
                    return
                task = ctx["tasks"][task_id]
                workpaper = ctx["runs"][task_id]["workpaper"]
                facts = {fact["fact_id"]: fact for fact in task["source"]["facts"]}
                table = "<table><tr><th>Claim</th><th>Submitted</th><th>Source value</th><th>Unit</th><th>Period</th></tr>"
                for claim in workpaper["claims"]:
                    fact = facts.get(claim["claim_id"])
                    table += "<tr>" + "".join(f"<td>{_h(value)}</td>" for value in (
                        claim["claim_id"], claim["value"], fact["value"] if fact else "Derived: verify formula",
                        claim["unit"], claim.get("end", task["protocol"]["period_end"]))) + "</tr>"
                table += "</table>"
                outcome = rows[task_id]["outcome"]
                actions = "<option>ADJUDICATE</option>" if outcome == "AWAITING_ADJUDICATION" else "<option>REVIEW</option>"
                decisions = "<option>ACCEPT</option><option>REJECT</option>" + ("" if outcome == "AWAITING_ADJUDICATION" else "<option>CORRECTION_REQUIRED</option>")
                form = (f"<h2>Record a review for {_h(task_id)}</h2><form method='post' action='/review'>"
                        f"<input type='hidden' name='token' value='{_h(token)}'>"
                        f"<input type='hidden' name='task_id' value='{_h(task_id)}'>"
                        "<label>Reviewer alias<input name='reviewer' maxlength='64' required></label>"
                        f"<label>Action<select name='action'>{actions}</select></label>"
                        f"<label>Decision<select name='decision'>{decisions}</select></label>"
                        "<label>Minutes<input name='minutes' type='number' min='0' max='1440' required></label>"
                        "<label>Reason or correction request<textarea name='note' maxlength='2000'></textarea></label>"
                        "<label>Finding claim (required for correction)<select name='claim_id'><option value=''>None</option>" +
                        "".join(f"<option value='{_h(claim['claim_id'])}'>{_h(claim['claim_id'])}</option>" for claim in workpaper["claims"]) +
                        "</select></label>"
                        "<label>Finding severity<select name='severity'><option>MATERIAL</option><option>MINOR</option></select></label>"
                        "<label>Proposed value, if any<input name='proposed_value' maxlength='200'></label>"
                        "<button type='submit'>Append review event</button></form>")
                if outcome not in ("AWAITING_TWO_REVIEWS", "AWAITING_ADJUDICATION"):
                    form = "<p>This version's review is closed. Corrections require a new workpaper version.</p>"
                success = "<p class='ok'>Review event recorded.</p>" if parse_qs(parsed.query).get("recorded") == ["1"] else ""
                content = (f"<p><a href='/'>All tasks</a> · {_h(rows[task_id]['outcome'])}"
                           f" · {rows[task_id]['primary_reviews']}/2 primary reviews</p>" + success +
                           f"<p>Workpaper SHA-256: <code>{_h(ctx['runs'][task_id]['workpaper_sha256'])}</code></p>"
                           f"<p>Filing accession: {_h(task['source']['accession'])}; source: <a href='{_h(task['source']['source_url'])}'>SEC Company Facts</a></p>"
                           + "<div class='table-wrap'>" + table + "</div>" + form)
                self._send(200, self._page(content))
            except (ValueError, OSError, KeyError) as exc:
                self._send(500, self._page(f"<p>Local data error: {_h(exc)}</p>"))

        def do_POST(self) -> None:
            if self.path != "/review":
                self._send(404, self._page("<p>Not found.</p>"))
                return
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{port}"
            if origin not in (None, expected_origin) or self.headers.get("Host") != f"127.0.0.1:{port}":
                self._send(403, self._page("<p>Forbidden origin or host.</p>"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("request size is invalid")
                fields = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True)
                if any(len(values) != 1 for values in fields.values()) or fields.get("token") != [token]:
                    raise ValueError("form token or fields are invalid")
                def one(name: str) -> str:
                    return fields.get(name, [""])[0]
                task_id = one("task_id")
                finding = ([{"claim_id": one("claim_id"), "severity": one("severity"),
                             "reason": one("note"), "proposed_value": one("proposed_value") or None}]
                           if one("claim_id") else [])
                append_event(config_path, events_path, task_id, one("reviewer"), one("action"),
                             one("decision"), int(one("minutes")), one("note"), findings=finding)
                self.send_response(303)
                self.send_header("Location", f"/task?task_id={quote(task_id)}&recorded=1")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (ValueError, OSError, KeyError) as exc:
                self._send(400, self._page(f"<p>Review was not recorded: {_h(exc)}</p>"))

    server = HTTPServer(("127.0.0.1", port), ReviewHandler)
    print(f"Acceptance Ledger local review: http://127.0.0.1:{port}/")
    print("Reviewer aliases are not authenticated. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
