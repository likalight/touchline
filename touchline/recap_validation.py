"""Independent typed checks for recap claims before rendering or translation."""
from collections import Counter


def verify_recap(state, recap, storyline=None):
    try:
        return _verify_recap(state, recap, storyline)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return {"status": "blocked", "checks": 0, "issues": ["Malformed or incomplete recap claims"],
                "scope": "typed recap claims; invalid input withheld before rendering"}


def _verify_recap(state, recap, storyline=None):
    issues, checks = [], 0
    goals = [e for e in state.events.values() if e.type == "goal"]
    score = {side: sum(e.team == side for e in goals) for side in ("home", "away")}
    names = {"home": state.meta.home.name, "away": state.meta.away.name}
    win = "home" if score["home"] > score["away"] else "away"
    lose = "away" if win == "home" else "home"
    draw = score["home"] == score["away"]

    def equal(actual, expected, label):
        nonlocal checks
        checks += 1
        if actual != expected:
            issues.append(label)

    equal(recap.get("score"), score, "recap score differs from goal record")
    equal(recap.get("t"), state.t, "recap snapshot time mismatch")
    for side in ("home", "away"):
        equal(recap.get(side), state.team_summary(side), f"{side} aggregates mismatch")
    equal(recap.get("players"), state.top_players(3), "player summary mismatch")
    for fr in [recap["headline"], *recap["reasons"]]:
        k, p = fr["k"], fr["p"]
        evs = [state.events[eid] for eid in fr.get("ev", []) if eid in state.events]
        equal(len(evs), len(fr.get("ev", [])), f"{k}: unknown evidence")
        equal(all(e.t <= state.t for e in evs), True, f"{k}: future evidence")
        expected = None
        if k == "rc.lead.win":
            equal(draw, False, "winner claimed for a draw")
            expected = dict(winner=names[win], loser=names[lose], score=f"{score[win]}-{score[lose]}")
        elif k == "rc.lead.draw":
            equal(draw, True, "draw claimed for unequal score")
            expected = dict(home=names["home"], away=names["away"], score=f"{score['home']}-{score['away']}")
        elif k in ("rc.upset", "rc.deserved"):
            xw, xl = (round(state.team[side]["xg"], 2) for side in (win, lose))
            equal(k, "rc.upset" if xw < xl else "rc.deserved", "xG comparison direction mismatch")
            expected = dict(winner=names[win], xg_w=xw, xg_l=xl)
        elif k == "rc.draw_xg":
            expected = dict(xg_h=round(state.team["home"]["xg"], 2), xg_a=round(state.team["away"]["xg"], 2))
        elif k == "rc.hat_trick":
            players = {e.player_id for e in evs if e.type == "goal"}
            equal(len(players), 1, "hat trick mixes scorers")
            if len(players) == 1:
                pid = next(iter(players))
                n = sum(g.player_id == pid for g in goals)
                equal(n >= 3, True, "hat trick below three goals")
                expected = dict(player=state.name(pid), goals=n)
        elif k == "rc.late":
            if evs:
                e = evs[0]
                equal(e.type == "goal" and e.team == win and e.minute >= 80 and abs(score[win]-score[lose]) == 1,
                      True, "late winner unsupported")
                expected = dict(player=state.name(e.player_id), minute=e.minute)
        elif k == "rc.comeback":
            running = {"home": 0, "away": 0}
            trailed = False
            for e in goals:
                running[e.team] += 1
                trailed |= running[win] < running[lose]
            equal(not draw and trailed, True, "comeback unsupported")
            expected = dict(team=names[win])
        elif k == "rc.turning":
            if evs and evs[0].team:
                e = evs[0]
                en = state.enriched[e.id]
                expected = dict(minute=e.minute, player=state.name(e.player_id) or names[e.team], team=names[e.team],
                                before_pct=round(en.wp_before[e.team]*100), after_pct=round(en.wp_after[e.team]*100))
        elif k == "rc.phase":
            phases = Counter(x["phase"] for x in state.timeline)
            side = "home" if phases["home_control"] >= phases["away_control"] else "away"
            total = sum(phases.values()) or 1
            expected = dict(team=names[side], control_pct=round(100*phases[f"{side}_control"]/total),
                            chaos_pct=round(100*phases["chaos"]/total))
        elif k == "rc.standout":
            best = state.top_players(1)[0]
            expected = {x: best[y] for x, y in (("player", "name"), ("rating", "rating"),
                                               ("xt_added", "xt_added"), ("pass_accuracy", "pass_accuracy"))}
        elif k == "rc.records":
            shot, sprint = state.records.get("fastest_shot_kmh", {}), state.records.get("top_speed_kmh", {})
            expected = dict(speed_kmh=shot.get("value"), player=shot.get("player"),
                            top_kmh=sprint.get("value"), top_player=sprint.get("player"))
            equal(set(fr["ev"]), {shot.get("event_id"), sprint.get("event_id")}, "record evidence mismatch")
        elif k in ("s.error", "s.redemption", "s.comeback", "rc.ten_men") and storyline:
            equal(storyline.recount(fr), None, f"{k}: story recount failed")
            expected = p  # recount independently validates the story parameters
        if expected is None:
            issues.append(f"{k}: unsupported or incomplete recap claim")
        else:
            equal(p, expected, f"{k}: claim parameters mismatch")
    for point in recap.get("turning_points", []):
        en = state.enriched.get(point.get("event_id"))
        if en is None or not en.ev.team:
            issues.append("unknown turning point")
            continue
        equal(point, {"event_id": en.ev.id, "minute": en.ev.minute, "player": en.player_name,
                      "team": en.ev.team, "type": en.ev.type, "before": en.wp_before[en.ev.team],
                      "after": en.wp_after[en.ev.team]}, "turning point values mismatch")
    return {"status": "blocked" if issues else "verified", "checks": checks, "issues": issues,
            "scope": "typed recap claims against current event record and derived model estimates"}
