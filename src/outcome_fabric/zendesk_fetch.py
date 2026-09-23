"""Read-only, bounded Zendesk OAuth collector for private pilot snapshots.

Only a small ticket projection is retained. Successful API authentication does
not establish customer permission, review identity, or source completeness.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 10_000_000
MAX_PAGES = 1000
SUBDOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
ENDPOINT = "/api/v2/incremental/tickets/cursor.json"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Zendesk redirected an authenticated request")


def _read_http(url: str, token: str) -> bytes:
    opener = build_opener(_NoRedirect)
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with opener.open(request, timeout=30) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Zendesk response exceeds the bounded page size")
    return raw


def _validate_url(url: str, subdomain: str) -> None:
    parsed = urlsplit(url)
    expected_host = f"{subdomain}.zendesk.com"
    if (parsed.scheme != "https" or parsed.hostname != expected_host or parsed.netloc != expected_host
            or parsed.path != ENDPOINT or parsed.fragment or not parsed.query):
        raise ValueError("cursor URL is outside the exact Zendesk endpoint")
    query = parse_qs(parsed.query, strict_parsing=True)
    if not set(query) <= {"start_time", "cursor", "per_page"} or any(len(values) != 1 for values in query.values()):
        raise ValueError("cursor URL has unexpected query parameters")
    if ("cursor" in query) == ("start_time" in query):
        raise ValueError("cursor URL must contain exactly one pagination token")


def _write_private(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)


def collect(subdomain: str, start_time: int, output_dir: Path, token: str,
            transport: Callable[[str, str], bytes] = _read_http) -> dict:
    if not isinstance(subdomain, str) or not SUBDOMAIN.fullmatch(subdomain):
        raise ValueError("Zendesk subdomain is invalid")
    if isinstance(start_time, bool) or not isinstance(start_time, int) or not 0 < start_time < int(time.time()) - 60:
        raise ValueError("start_time must be a past Unix timestamp older than one minute")
    if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
        raise ValueError("OAuth bearer token is missing or invalid")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("output directory already exists; refusing to overwrite private evidence")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".zendesk-fetch-", dir=output_dir.parent))
    url = f"https://{subdomain}.zendesk.com{ENDPOINT}?{urlencode({'start_time': start_time})}"
    seen = set()
    pages = []
    try:
        for index in range(MAX_PAGES):
            _validate_url(url, subdomain)
            if url in seen:
                raise ValueError("Zendesk repeated a cursor URL")
            seen.add(url)
            raw = transport(url, token)
            if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Zendesk response is not bounded bytes")
            page = json.loads(raw)
            if not isinstance(page, dict) or not isinstance(page.get("tickets"), list) or len(page["tickets"]) > 1000 or not isinstance(page.get("end_of_stream"), bool):
                raise ValueError("Zendesk page contract is invalid")
            tickets = []
            for ticket in page["tickets"]:
                if not isinstance(ticket, dict):
                    raise ValueError("Zendesk ticket is invalid")
                projected = {name: ticket.get(name) for name in ("id", "status", "updated_at")}
                if isinstance(projected["id"], bool) or not isinstance(projected["id"], int) or projected["id"] < 1:
                    raise ValueError("Zendesk ticket ID is invalid")
                if not isinstance(projected["status"], str) or not isinstance(projected["updated_at"], str):
                    raise ValueError("Zendesk ticket status or timestamp is invalid")
                tickets.append(projected)
            projected_page = {"tickets": tickets, "end_of_stream": page["end_of_stream"]}
            projected_raw = (json.dumps(projected_page, sort_keys=True, separators=(",", ":")) + "\n").encode()
            name = f"page-{index:04d}.json"
            _write_private(staging / name, projected_raw)
            pages.append({"path": name, "sha256": hashlib.sha256(projected_raw).hexdigest(),
                          "raw_response_sha256": hashlib.sha256(raw).hexdigest(), "ticket_rows": len(tickets)})
            if page["end_of_stream"]:
                break
            next_url = page.get("after_url") or page.get("next_page")
            if not isinstance(next_url, str):
                raise ValueError("incomplete Zendesk page has no next cursor URL")
            _validate_url(next_url, subdomain)
            url = next_url
        else:
            raise ValueError("Zendesk export exceeds the maximum page count")
        receipt = {"schema_version": "0.1.0", "source": "ZENDESK_OAUTH_BEARER_INCREMENTAL_TICKETS",
                   "subdomain": subdomain, "start_time": start_time, "end_of_stream": True,
                   "pages": pages,
                   "scope": "API_RESPONSE_DIGESTS_AND_MINIMAL_LOCAL_PROJECTION_ONLY_NOT_PERMISSION_OR_REVIEW_AUTHENTICATION"}
        _write_private(staging / "collection-receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        if output_dir.exists():
            raise ValueError("output directory appeared during collection")
        staging.rename(output_dir)
        return receipt
    except Exception:
        shutil.rmtree(staging)
        raise
