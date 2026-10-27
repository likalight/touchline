"""FactChecker - validates supported structured claims against match state.

Two layers:
1. Frame checks: every cited event exists and is not from the future; every numeric
   parameter that has a ground-truth counterpart (xG, difficulty, speeds, distances,
   win probability) is recomputed from the state and must match.
2. Text checks (for LLM-written copy): every number in the text must be one of the
   numbers the frames allow, and no player outside the insight may be named.
"""
from __future__ import annotations

import re
from string import Formatter
from typing import Iterable

from touchline.analytics.state import MatchState

# a number, including ordinals ("99th", "2º") and run-on units ("29.7km/h", "16m", "3x")
# claims a match feed cannot support unless a verified frame says so ("best ever", "a club record")
SUPERLATIVE_RE = re.compile(r"\b(best|worst|greatest|finest|record|ever|historic|of the season|of the year|of all time|"
                            r"unprecedented|career|mejor|peor|r[eé]cord|historique|meilleur|pire|melhor|pior|hist[oó]ric[oa])\b", re.I)
NUM_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?:st|nd|rd|th|º|ª|er|e|km|m|s|x)?(?![\w])")


def _num(v) -> list[str]:
    out = []
    if isinstance(v, bool):
        return out
    if isinstance(v, (int, float)):
        out.append(f"{v}")
        if isinstance(v, float):
            out += [f"{v:.1f}", f"{v:.2f}", f"{v:.3f}", f"{round(v)}"]
            if v.is_integer():
                out.append(str(int(v)))
    return [o.rstrip("0").rstrip(".") if "." in o else o for o in out] + out


class FactChecker:
    name = "FactChecker"
    role = "Binds structured claims to source events and checks supported derived values"

    def __init__(self, state: MatchState):
        self.s = state
        self.storyline = None  # StorylineKeeper, for independent recounts of story claims
        self.passed = 0
        self.blocked = 0
        self.corrected = 0

    # ------------------------------------------------------------------ frames
    def _bindings(self, fr: dict, ins: dict) -> tuple[int, list[str]]:
        """Independent entity/outcome bindings; token membership is insufficient.

        Aggregate headlines deliberately do not inherit the latest event's actor.
        Their identities come from the declared aggregate or recounted story frame.
        """
        from touchline.i18n import BANKS

        k, p, ids = fr["k"], fr["p"], fr["ev"]
        issues, checks = [], 0
        if k not in BANKS["en"] or not k.startswith(("h.", "r.", "s.", "rc.")):
            return 1, [f"unsupported frame {k}"]
        required = {field for key, template in BANKS["en"].items()
                    if key == k or key.startswith(k + ".")
                    for _, field, _, _ in Formatter().parse(template) if field}
        if required - p.keys():
            issues.append(f"{k}: missing parameters {sorted(required - p.keys())}")
            checks += 1
        if not ids:
            return 1, [f"{k}: claim without evidence"]
        ev = self.s.events.get(ids[0])
        if ev is None:
            return 0, []  # the citation pass reports this

        def equal(field, value):
            nonlocal checks
            checks += 1
            if field not in p or p[field] != value:
                issues.append(f"{k}: {field} does not match source {ev.id}")

        kinds = {
            "h.goal": ("goal",), "h.chance_saved": ("shot",), "h.chance_missed": ("shot",),
            "h.chance_blocked": ("shot",), "h.line_break": ("pass",), "h.hard_pass": ("pass",),
            "h.sprint": ("carry", "dribble"), "h.long_carry": ("carry", "dribble"), "h.card_red": ("card",),
            "h.card_yellow": ("card",), "h.brace": ("goal",), "h.hat_trick": ("goal",),
            "h.saves": ("save",), "h.record_shot": ("shot",), "h.half_time": ("half_time",),
            "h.full_time": ("full_time",), "r.assist": ("pass",), "r.chance_quality": ("shot",),
            "r.pass_stats": ("pass",), "r.pass_rarity": ("pass",), "r.bypassed": ("pass",),
        }
        if k in kinds:
            checks += 1
            if ev.type not in kinds[k]:
                issues.append(f"{k}: wrong source event type {ev.type}")
        player_keys = {"h.goal", "h.chance_saved", "h.chance_missed", "h.chance_blocked", "h.line_break",
                       "h.hard_pass", "h.sprint", "h.long_carry", "h.card_red", "h.card_yellow",
                       "h.brace", "h.hat_trick", "h.saves", "h.focus_touch", "r.location",
                       "r.finishing_over", "r.finishing_under"}
        if k in player_keys:
            equal("player", self.s.name(ev.player_id) or "")
        if k == "h.goal":
            equal("team", self.s.meta.home.name if ev.team == "home" else self.s.meta.away.name)
        outcomes = {"h.chance_saved": {"saved"}, "h.chance_missed": {"off_target", "woodwork", "missed"},
                    "h.chance_blocked": {"blocked"}, "h.card_red": {"red", "second_yellow"},
                    "h.card_yellow": {"yellow"}, "h.line_break": {"complete"}, "h.hard_pass": {"complete"}}
        if k in outcomes:
            checks += 1
            if ev.outcome not in outcomes[k]:
                issues.append(f"{k}: outcome does not match source {ev.id}")
        if k == "h.chance_saved":
            keeper = ev.qualifiers.get("goalkeeper_id")
            if not keeper:
                save = next((e for e in self.s.events.values() if e.type == "save" and e.t >= ev.t
                             and e.seq in (ev.seq + 1, ev.seq + 2)), None)
                keeper = save.player_id if save else None
            equal("keeper", self.s.name(keeper) or "")
        if k == "r.assist":
            equal("assister", self.s.name(ev.player_id) or "")
            checks += 1
            if ev.outcome != "complete":
                issues.append("r.assist: pass was not completed")
        if k in ("h.brace", "h.hat_trick", "r.finishing_over", "r.finishing_under"):
            goals = sum(e.type == "goal" and e.player_id == ev.player_id and e.t <= ins["t"]
                        for e in self.s.events.values())
            if k.startswith("r."):
                equal("goals", goals)
            else:
                checks += 1
                if goals != (2 if k == "h.brace" else 3):
                    issues.append(f"{k}: goal total does not match source")
        if k in ("h.half_time", "h.full_time"):
            equal("home", self.s.meta.home.name)
            equal("away", self.s.meta.away.name)
            for side in ("home", "away"):
                equal(f"score_{side}", sum(e.type == "goal" and e.team == side and e.t <= ev.t
                                          for e in self.s.events.values()))
        if k == "h.record_shot":
            equal("speed_kmh", ev.qualifiers.get("shot_speed_kmh"))
        if k == "h.saves":
            equal("count", sum(e.type == "save" and e.player_id == ev.player_id and e.t <= ev.t
                               for e in self.s.events.values()))
        # Story headlines must name the same roles as their separately recounted reason.
        if k.startswith("h.story_"):
            reason_key = "s." + k.removeprefix("h.story_")
            reason = next((r for r in ins["reasons"] if r["k"] == reason_key), None)
            checks += 1
            expected = dict(reason["p"]) if reason else {}
            if k == "h.story_keeper":
                keeper = next((pl for pl in self.s.players.values() if pl.name == expected.get("keeper")), None)
                if keeper:
                    expected["team"] = self.s.meta.home.name if keeper.team == "home" else self.s.meta.away.name
            if reason is None or any(expected.get(key) != value for key, value in p.items()):
                issues.append(f"{k}: headline disagrees with story evidence")
        return checks, issues

    def check_insight(self, ins: dict) -> dict:
        s = self.s
        issues: list[str] = []
        checks = 0
        for fr in [ins["headline"]] + ins["reasons"]:
            binding_checks, binding_issues = self._bindings(fr, ins)
            checks += binding_checks
            issues.extend(binding_issues)
            for eid in fr["ev"]:
                checks += 1
                ev = s.events.get(eid)
                if ev is None:
                    issues.append(f"{fr['k']}: unknown event {eid}")
                elif ev.t > ins["t"] + 1.0:
                    issues.append(f"{fr['k']}: cites future event {eid}")
            if fr["k"] not in ("r.buildup",) and fr["k"].startswith("r.") and not fr["ev"]:
                issues.append(f"{fr['k']}: claim without evidence")
            if (fr["k"].startswith("s.") or fr["k"] == "rc.ten_men") and self.storyline is not None and all(i in s.events for i in fr["ev"]):
                checks += 1
                try:
                    issue = self.storyline.recount(fr)
                except (KeyError, TypeError, IndexError):
                    issue = f"{fr['k']}: malformed story claim"
                if issue:
                    issues.append(issue)
                continue
            p = fr["p"]
            ev = s.events.get(fr["ev"][0]) if fr["ev"] else None
            en = s.enriched.get(ev.id) if ev else None
            if en is None:
                continue
            if "xg" in p and fr["k"] == "r.chance_quality":
                checks += 1
                if en.xg is None or abs(round(en.xg, 2) - p["xg"]) > 0.006:
                    issues.append(f"xg mismatch on {ev.id}")
                checks += 1
                if en.xg is None or p.get("xg_pct") != round(en.xg * 100):
                    issues.append(f"xg percentage mismatch on {ev.id}")
            if fr["k"] == "r.pass_rarity" and en.pass_prob is not None:
                checks += 1
                if round(en.pass_prob * 100) != p["prob_pct"]:
                    issues.append(f"pass probability mismatch on {ev.id}")
            if "difficulty" in p and fr["k"] == "r.pass_stats":
                checks += 1
                if en.difficulty is None or abs(round(en.difficulty * 100) - p["difficulty"]) > 0:
                    issues.append(f"difficulty mismatch on {ev.id}")
                checks += 1
                if en.pass_prob is None or p.get("prob_pct") != round(en.pass_prob * 100):
                    issues.append(f"pass probability mismatch on {ev.id}")
            if fr["k"] == "r.assist":
                checks += 1
                if en.difficulty is None or p.get("difficulty") != round(en.difficulty * 100):
                    issues.append(f"assist difficulty mismatch on {ev.id}")
            if fr["k"] == "r.bypassed":
                checks += 1
                if p.get("bypassed") != en.bypassed:
                    issues.append(f"bypassed opponents mismatch on {ev.id}")
            for q in ("distance_m", "ball_speed_kmh", "shot_speed_kmh", "speed_kmh"):
                if q in p and q in ev.qualifiers and fr["k"] in ("r.pass_stats", "r.save_speed", "r.carry_speed", "h.sprint", "h.long_carry"):
                    checks += 1
                    if abs(float(ev.qualifiers[q]) - float(p[q])) > 0.051:
                        issues.append(f"{q} mismatch on {ev.id}")
            if fr["k"] in ("r.wp_swing", "r.card_wp") and en.wp_after:
                checks += 3
                side = {s.meta.home.name: "home", s.meta.away.name: "away"}.get(p.get("team"))
                if side is None or (fr["k"] == "r.card_wp" and side != ev.team):
                    issues.append(f"win-probability team mismatch on {ev.id}")
                elif (p.get("after_pct") != round(en.wp_after[side] * 100)
                      or p.get("before_pct") != round(en.wp_before[side] * 100)):
                    issues.append(f"win-prob mismatch on {ev.id}")
        ok = not issues
        if ok:
            self.passed += 1
        else:
            self.blocked += 1
        return {"status": "verified" if ok else "blocked", "checks": checks, "issues": issues,
                "scope": "Source citations, supported frame identities/outcomes and derived-value checks; not general prose entailment."}

    # ------------------------------------------------------------------ text
    def allowed_numbers(self, ins: dict) -> set[str]:
        allowed: set[str] = set()
        for fr in [ins["headline"]] + ins["reasons"]:
            for v in fr["p"].values():
                allowed.update(_num(v))
        allowed.update(_num(ins["minute"]))
        allowed.update(str(v) for v in ins.get("score", {}).values())
        allowed.update({"90", "45"})  # halves; window lengths come from the templates below
        # numbers written into the verified phrase templates themselves ("in the last 15 minutes")
        from touchline.i18n import BANKS

        for fr in [ins["headline"]] + ins["reasons"]:
            for bank in BANKS.values():
                tpl = bank.get(fr["k"])
                if isinstance(tpl, str):
                    allowed.update(NUM_RE.findall(re.sub(r"\{[^}]*\}", "", tpl)))
        return allowed

    def names_in(self, ins: dict) -> set[str]:
        # any player the verified frames name, under any role (scorer, keeper, duel attacker, the player who lost the ball...)
        known = {p.name for p in self.s.players.values()}
        names = set()
        for fr in [ins["headline"]] + ins["reasons"]:
            for v in fr["p"].values():
                if isinstance(v, str) and v in known:
                    names.add(v)
        return names

    def check_text(self, ins: dict, texts: Iterable[str]) -> list[str]:
        allowed = self.allowed_numbers(ins)
        named = self.names_in(ins)
        issues = []
        from touchline.i18n import BANKS

        frame_text = " ".join(str(b.get(fr["k"], "")) for fr in [ins["headline"]] + ins["reasons"] for b in BANKS.values())
        for text in texts:
            for w in {m.group(0).lower() for m in SUPERLATIVE_RE.finditer(text)}:
                if not re.search(rf"\b{re.escape(w)}\b", frame_text, re.I):
                    issues.append(f"unsupported superlative '{w}'")
            for n in NUM_RE.findall(text):
                n2 = n.replace(",", ".")
                normalized = n2.rstrip("0").rstrip(".") if "." in n2 else n2
                if n2 not in allowed and normalized not in allowed:
                    issues.append(f"unsupported number '{n}'")
            named_last = {n.split()[-1] for n in named}
            for p in self.s.players.values():
                if p.name in named:
                    continue
                last = p.name.split()[-1]
                # a shared surname only counts when the full name is used
                if p.name in text or (last not in named_last and re.search(rf"\b{re.escape(last)}\b", text)):
                    issues.append(f"unsupported player '{p.name}'")
        return issues

    @staticmethod
    def _nums(text: str) -> set[str]:
        out = set()
        for n in NUM_RE.findall(text):
            n = n.replace(",", ".")
            out.add(n.rstrip("0").rstrip(".") if "." in n else n)
        return out

    def check_rewrite(self, base: list[str], rewrite: list[str]) -> list[str]:
        """Conservative per-line number and entity preservation, not semantic entailment.

        Preserve multiplicity AND order: a set cannot distinguish a score of 2-1
        from 2-2, or a stat from a time window. Reordered translations may fall back
        to the phrase bank; never accept an uncertain association as verified.
        """
        issues = []
        if len(base) != len(rewrite):
            issues.append("rewrite changed the number of source lines")
        names = [p.name for p in self.s.players.values()] + [self.s.meta.home.name, self.s.meta.away.name]
        names_re = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b", re.I)

        def numbers(text):
            tokens = (n.replace(",", ".") for n in NUM_RE.findall(text))
            return tuple(n.rstrip("0").rstrip(".") if "." in n else n for n in tokens)

        for i, new in enumerate(rewrite):
            ref = base[i] if i < len(base) else ""
            if numbers(new) != numbers(ref):
                issues.append("number values, repetitions or order differ from the verified source line")
            if tuple(m.group().casefold() for m in names_re.finditer(new)) != tuple(m.group().casefold() for m in names_re.finditer(ref)):
                issues.append("player/team identity or order differs from the verified source line")
        return issues

    def stats(self) -> dict:
        return {"verified": self.passed, "blocked": self.blocked, "llm_rewrites_rejected": self.corrected}
