"""Touchline packages: the event-driven back office (Azure Functions, Flex Consumption).

* `on_insight`  Event Hubs trigger on `touchline-insights` (the web app's outbound stream).
                 Goals become social cards; full time becomes the post-match package
                 (recaps in four languages and two personas, highlights edit list, top players,
                 verification summary), written to Blob Storage for a CMS or social tool to pick up.
* `packages`     HTTP: the latest packages, for the ops panel and partners.
* Teams          At full time, an Adaptive Card with the result, the match story and the top players is
                 posted to a Microsoft Teams channel (TEAMS_WEBHOOK_URL, a Teams Workflows webhook).
* `watchdog`     Timer, every 5 minutes: checks the live demo is healthy and logs it to
                 Application Insights (alert on `touchline_up == 0`).

Identity: the same user-assigned managed identity as the web app; no keys or connection strings.
"""
from __future__ import annotations

import datetime as dt
import json
import hashlib
import logging
import os

import azure.functions as func
import httpx
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

app = func.FunctionApp()
WEB = os.environ.get("TOUCHLINE_WEB_URL", "").rstrip("/")
CONTAINER = os.environ.get("PACKAGES_CONTAINER", "packages")
log = logging.getLogger("touchline.packages")


def _blobs():
    cred = DefaultAzureCredential(managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID"))
    return BlobServiceClient(f"https://{os.environ['PACKAGES_STORAGE_ACCOUNT']}.blob.core.windows.net", credential=cred) \
        .get_container_client(CONTAINER)


def _put(c, name: str, data: dict) -> None:
    c.upload_blob(name, json.dumps(data, ensure_ascii=False, indent=1), overwrite=True,
                  content_settings=ContentSettings(content_type="application/json"))


def teams_card(pkg: dict, app_url: str = "") -> dict:
    """An Adaptive Card for the full-time package, in the Teams Workflows webhook format."""
    recap = (pkg.get("recaps", {}).get("casual", {}).get("en") or {})
    facts = [{"title": p["name"], "value": f"rating {p['rating']}"} for p in pkg.get("top_players", [])[:3]]
    body = [
        {"type": "TextBlock", "text": "Full time", "weight": "Bolder", "color": "Accent", "size": "Small"},
        {"type": "TextBlock", "text": f"{pkg['home']} {pkg['score']['home']}-{pkg['score']['away']} {pkg['away']}", "weight": "Bolder", "size": "ExtraLarge", "wrap": True},
        {"type": "TextBlock", "text": recap.get("title", ""), "weight": "Bolder", "wrap": True, "spacing": "Medium"},
        *[{"type": "TextBlock", "text": f"• {l['text'] if isinstance(l, dict) else l}", "wrap": True, "spacing": "Small"} for l in recap.get("lines", [])[:4]],
        {"type": "FactSet", "facts": facts, "spacing": "Medium"},
        {"type": "TextBlock", "text": f"{pkg['verification']['verified']} of {pkg['verification']['insights']} insights checked against the match data. Synthetic match, fictional clubs.",
         "isSubtle": True, "size": "Small", "wrap": True},
    ]
    actions = [{"type": "Action.OpenUrl", "title": "Open the match", "url": f"{app_url}/?session={pkg['session']}"}] if app_url else []
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
        "body": body, "actions": actions}}]}


@app.event_hub_message_trigger(arg_name="events", event_hub_name="touchline-insights", connection="EventHubConnection",
                               consumer_group="packages", cardinality=func.Cardinality.MANY)
def on_insight(events: list[func.EventHubEvent]) -> None:
    c = _blobs()
    for e in events:
        try:
            m = json.loads(e.get_body().decode("utf-8"))
        except Exception:
            log.warning("skipping malformed message")
            continue
        mid = m.get("match_id", "unknown")
        if m.get("type") == "insight" and m.get("kind") in ("goal", "hat_trick", "card_red"):
            card = {"schema": "touchline.social/1", "match_id": mid, "minute": m["minute"], "kind": m["kind"],
                    "copy": m.get("copy", {}), "evidence": m.get("evidence", []), "checked": m.get("verification") == "verified"}
            _put(c, f"{mid}/social/{m['minute']:03d}-{m['id']}.json", card)
            log.info("social card %s %s", mid, m["kind"])
        if m.get("type") == "full_time":
            snapshot = m.get("package")
            if snapshot is None:  # backwards compatibility, with identity validation
                if not WEB:
                    raise ValueError("Full-time message requires a package snapshot")
                r = httpx.get(f"{WEB}/api/matches/{m['session']}/package", timeout=30)
                r.raise_for_status()
                snapshot = r.json()
            if (snapshot.get("match_id") != mid or snapshot.get("session") != m.get("session")
                    or not snapshot.get("complete")):
                raise ValueError("Package does not belong to this completed match")
            stamp = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
            pkg = {**snapshot, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(), "built_by": "touchline-packages (Azure Functions)"}
            _put(c, f"{mid}/package-{stamp}.json", pkg)
            _put(c, f"{mid}/latest.json", pkg)
            _put(c, "latest.json", {"match_id": mid, "score": pkg["score"], "home": pkg["home"], "away": pkg["away"],
                                    "built_at": pkg["built_at"], "blob": f"{mid}/latest.json"})
            log.info("post-match package %s %s", mid, pkg["score"])
            hook = os.environ.get("TEAMS_WEBHOOK_URL")
            if hook:
                try:
                    httpx.post(hook, json=teams_card(pkg, WEB), timeout=15).raise_for_status()
                    log.info("posted full-time card to Teams for %s", mid)
                except Exception as exc:
                    log.warning("Teams post failed: %s", exc)


@app.route(route="packages", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
def packages(req: func.HttpRequest) -> func.HttpResponse:
    c = _blobs()
    latest = None
    try:
        latest = json.loads(c.download_blob("latest.json").readall())
    except Exception:
        pass
    names = sorted((b.name for b in c.list_blobs() if b.name.endswith(".json")), reverse=True)
    social = [n for n in names if "/social/" in n][:10]
    built = [n for n in names if "/package-" in n]
    body = {"latest": latest, "packages_built": len(built), "recent_packages": built[:5], "recent_social_cards": social}
    return func.HttpResponse(json.dumps(body), mimetype="application/json")


@app.timer_trigger(arg_name="timer", schedule="0 */5 * * * *", run_on_startup=False)
def watchdog(timer: func.TimerRequest) -> None:
    up = 0
    try:
        h = httpx.get(f"{WEB}/api/health", timeout=10).json()
        up = int(h.get("status") == "ok")
        log.info("touchline_up=%d sessions=%s llm=%s", up, h.get("sessions"), (h.get("llm") or {}).get("backend"))
    except Exception as exc:
        log.error("touchline_up=0 health check failed: %s", exc)
    if not up:
        log.error("touchline_up=0")
