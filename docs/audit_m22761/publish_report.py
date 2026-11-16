#!/usr/bin/env python3
"""Publish /tmp/report.json to the platform report API (mission m22761).

Credentials come from TENSOR_AGENT_USER / TENSOR_AGENT_PASS, endpoint from
TENSOR_API_BASE; nothing is echoed back except the response body.
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("TENSOR_API_BASE", "http://127.0.0.1:8010/api/v1").rstrip("/")


def post(path: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read() or b"{}")


def main() -> int:
    login = post(
        "/auth/login",
        {
            "username": os.environ["TENSOR_AGENT_USER"],
            "password": os.environ["TENSOR_AGENT_PASS"],
        },
    )
    token = login.get("access_token") or login.get("token") or ""
    print("login ok, token length", len(token))
    with open("/tmp/report.json", encoding="utf-8") as fh:
        payload = json.load(fh)
    result = post("/tensor/reports", payload, token)
    print(json.dumps(result, ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())