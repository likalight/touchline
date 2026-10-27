"""Roles forwarded by a separately configured, trusted authentication proxy.

Container Apps signs people in with Microsoft Entra ID (no auth code in the app) and forwards
the signed-in user as the `X-MS-CLIENT-PRINCIPAL` header. Fans stay anonymous; producer actions
need an app role:

* Touchline.Producer  approve or drop graphics, switch review mode, control the shared broadcast, run drills
* Touchline.Admin     everything a producer can do

TOUCHLINE_AUTH=entra enforces roles only when TOUCHLINE_TRUST_AUTH_PROXY=on.
That flag is safe only behind a verified identity gateway that removes client-supplied
principal headers and prevents direct access. The current public Express deployment
has no such gateway: it uses open viewing plus protected shared mutations.
Producer actions are currently retained in session memory, not a durable audit store.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

from fastapi import HTTPException, Request

ROLE_CLAIMS = ("roles", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role")
PRODUCER, ADMIN = "Touchline.Producer", "Touchline.Admin"


def mode() -> str:
    return "entra" if os.getenv("TOUCHLINE_AUTH", "open").lower() == "entra" else "open"


def principal(request: Request) -> dict:
    trusted = mode() == "entra" and os.getenv("TOUCHLINE_TRUST_AUTH_PROXY", "").lower() == "on"
    raw: Optional[str] = request.headers.get("x-ms-client-principal") if trusted else None
    if not raw:
        return {"signed_in": False, "name": None, "roles": [], "auth_mode": mode()}
    try:
        data = json.loads(base64.b64decode(raw, validate=True))
        if not isinstance(data, dict) or not isinstance(data.get("claims", []), list):
            raise ValueError("invalid principal")
        if any(not isinstance(c, dict) or not isinstance(c.get("val"), str) for c in data.get("claims", [])):
            raise ValueError("invalid claims")
    except Exception:
        return {"signed_in": False, "name": None, "roles": [], "auth_mode": mode()}
    claims = data.get("claims", [])
    get = lambda *t: next((c["val"] for c in claims if c.get("typ") in t), None)  # noqa: E731
    roles = sorted({c["val"] for c in claims if c.get("typ") in ROLE_CLAIMS})
    return {"signed_in": True, "name": get("name", "preferred_username", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"),
            "roles": roles, "auth_mode": mode()}


def can_produce(p: dict) -> bool:
    return mode() == "open" or PRODUCER in p["roles"] or ADMIN in p["roles"]


def require_producer(request: Request) -> dict:
    p = principal(request)
    if not can_produce(p):
        raise HTTPException(403 if p["signed_in"] else 401,
                            "producer role required" if p["signed_in"] else "sign in with Microsoft to use producer tools")
    return p


def actor(p: dict) -> str:
    return p["name"] or ("anonymous (open demo)" if mode() == "open" else "anonymous")
