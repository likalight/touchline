"""Read-only provenance for an existing insight; never reruns checks against later state."""
from __future__ import annotations


def build_receipt(session, insight, persona="casual", lang="en"):
    renders = insight.get("renders", {}).get(persona, {})
    render = renders.get(lang) or renders.get("en")
    evidence = []
    for eid in insight["event_ids"]:
        enriched = session.state.enriched.get(eid)
        if enriched is None or enriched.ev.t > insight["t"]:
            continue
        drivers = []
        if enriched.xg_features:
            drivers = session.state.models.xg.explain(enriched.xg_features, session.state.models.shot_baseline)
        elif enriched.pass_features:
            drivers = session.state.models.pass_.explain(enriched.pass_features, session.state.models.pass_baseline)
        evidence.append({"event_id": eid, "facts": enriched.facts(), "model_drivers": drivers})
    cue = insight.get("cue")
    return {
        "schema": "touchline.receipt/1", "synthetic": True, "session_id": session.id,
        "insight_id": insight["id"], "minute": insight["minute"], "render": render,
        "audiences": {p: insight.get("renders", {}).get(p, {}).get(lang)
                      or insight.get("renders", {}).get(p, {}).get("en") for p in ("casual", "analyst")},
        "claims": [{"key": frame["k"], "values": frame["p"], "event_ids": frame["ev"]}
                   for frame in [insight["headline"], *insight["reasons"]]],
        "evidence": evidence, "verification": insight["verification"],
        "agents": insight.get("agent_spans", []),
        "pipeline_ms": insight["latency_ms"],
        "timing_scope": "Server agent pipeline only; excludes model updates, speech and browser delivery.",
        "editorial": {"decision": cue.get("decision"), "approval": cue["approval"],
                      "cue_id": cue["cue_id"], "in_at_t": cue["in_at_t"], "out_at_t": cue["out_at_t"]} if cue else None,
        "scope": "Checks against synthetic match facts and model estimates, not a guarantee of real-world accuracy or translation equivalence.",
    }
