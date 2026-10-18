"""Who is calling: Microsoft Entra ID through Azure Container Apps built-in authentication.

Container Apps signs people in with Microsoft Entra ID (no auth code in the app) and forwards
the signed-in user as the `X-MS-CLIENT-PRINCIPAL` header. Fans stay anonymous; producer actions
need an app role:

* Touchline.Producer  approve or drop graphics, switch review mode, control the shared broadcast, run drills
* Touchline.Admin     everything a producer can do

TOUCHLINE_AUTH=entra enforces the roles (production). The default, `open`, lets anyone try the
producer tools, which is what a public judging demo needs; every action is still audited.
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
    raw: Optional[str] = request.headers.get("x-ms-client-principal")
    if not raw:
        return {"signed_in": False, "name": None, "roles": [], "auth_mode": mode()}
    try:
        data = json.loads(base64.b64decode(raw))
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
