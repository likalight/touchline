"""FactChecker - nothing reaches air unless it can be re-derived from the match state.

Two layers:
1. Frame checks: every cited event exists and is not from the future; every numeric
   parameter that has a ground-truth counterpart (xG, difficulty, speeds, distances,
   win probability) is recomputed from the state and must match.
2. Text checks (for LLM-written copy): every number in the text must be one of the
   numbers the frames allow, and no player outside the insight may be named.
"""
from __future__ import annotations

import re
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
    role = "Re-derives every claim from match state; blocks unverifiable copy"

    def __init__(self, state: MatchState):
        self.s = state
        self.storyline = None  # StorylineKeeper, for independent recounts of story claims
        self.passed = 0
        self.blocked = 0
        self.corrected = 0

    # ------------------------------------------------------------------ frames
    def check_insight(self, ins: dict) -> dict:
        s = self.s
        issues: list[str] = []
        checks = 0
        for fr in [ins["headline"]] + ins["reasons"]:
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
                issue = self.storyline.recount(fr)
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
            if fr["k"] == "r.pass_rarity" and en.pass_prob is not None:
                checks += 1
                if round(en.pass_prob * 100) != p["prob_pct"]:
                    issues.append(f"pass probability mismatch on {ev.id}")
            if "difficulty" in p and fr["k"] == "r.pass_stats":
                checks += 1
                if en.difficulty is None or abs(round(en.difficulty * 100) - p["difficulty"]) > 0:
                    issues.append(f"difficulty mismatch on {ev.id}")
            for q in ("distance_m", "ball_speed_kmh", "shot_speed_kmh", "speed_kmh"):
                if q in p and q in ev.qualifiers and fr["k"] in ("r.pass_stats", "r.save_speed", "r.carry_speed", "h.sprint", "h.long_carry"):
                    checks += 1
                    if abs(float(ev.qualifiers[q]) - float(p[q])) > 0.051:
                        issues.append(f"{q} mismatch on {ev.id}")
            if fr["k"] in ("r.wp_swing", "r.card_wp") and en.wp_after:
                checks += 1
                side = "home" if p.get("team") == s.meta.home.name else "away"
                if abs(round(en.wp_after[side] * 100) - p["after_pct"]) > 1:
                    issues.append(f"win-prob mismatch on {ev.id}")
        ok = not issues
        if ok:
            self.passed += 1
        else:
            self.blocked += 1
        return {"status": "verified" if ok else "blocked", "checks": checks, "issues": issues}

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
                if n2 not in allowed and n2.rstrip("0").rstrip(".") not in allowed:
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
        """Line-by-line binding for model rewrites: a rewritten line may only use the numbers of the verified
        line it rewrites (the title may use the title's). Stops a model swapping in a rounding neighbour or a
        number that belongs to a different fact of the same moment."""
        issues = []
        for i, new in enumerate(rewrite):
            ref = base[i] if i < len(base) else " ".join(base)
            extra = self._nums(new) - self._nums(ref)
            if extra:
                issues.append(f"number {sorted(extra)} not in the verified line it rewrites")
        return issues

    def stats(self) -> dict:
        return {"verified": self.passed, "blocked": self.blocked, "llm_rewrites_rejected": self.corrected}
