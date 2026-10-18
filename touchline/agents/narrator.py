"""Narrator - renders one insight into genuinely different experiences.

Personas
  casual   plain language, odds as "x% of the time", 2 lines max, no jargon
  analyst  every metric, model drivers, counterfactuals, league context
  studio   broadcast lower-third: short headline + one stat, producer-ready
  access   audio-description for blind / low-vision fans: spatial, spoken, no symbols

Deterministic phrase banks cover en/es/fr/pt offline. With an LLM backend, the
Narrator agent can polish copy or write any other language; its output is re-checked
by the FactChecker and discarded on any unsupported number or name.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

from touchline.agents.verifier import FactChecker
from touchline.i18n import BANKS, phrase, vocab
from touchline.llm import get_llm

PERSONAS = ["casual", "analyst", "studio", "access"]
MAX_LINES = {"casual": 2, "analyst": 6, "studio": 1, "access": 3}

NARRATOR_INSTRUCTIONS = """You are the on-air copywriter for a football studio graphics system.
You receive a structured insight (headline + reasons) already rendered in English and a
target persona and language. Rewrite it for that audience in the target language.
Rules: keep EVERY number and player name exactly as given; do not add facts, numbers or
players that are not in the input; keep the title under 60 characters and each line under
110 characters; casual = warm, plain, no jargon; studio = punchy broadcast lower-third;
analyst = precise; access = spoken audio description, no symbols or arrows.
Return only JSON: {"title": str, "lines": [str, ...]}"""


def _fmt(v, lang: str):
    if isinstance(v, str) and v.startswith("@"):
        return vocab(lang, v[1:])
    if isinstance(v, float):
        return f"{v:g}" if abs(v) >= 0.01 else f"{v:.3f}"
    return v


def _render_frame(fr: dict, lang: str, persona: str) -> str:
    tpl = phrase(lang, fr["k"], persona)
    params = defaultdict(str, {k: _fmt(v, lang) for k, v in fr["p"].items()})
    text = tpl.format_map(params)
    if persona == "access":
        text = text.replace("(+", "(up ").replace("%", " percent").replace("  ", " ")
    return text


class Narrator:
    name = "Narrator"
    role = "Persona- and language-specific storytelling"

    def __init__(self, checker: FactChecker):
        self.checker = checker
        self.llm = get_llm()
        self.llm_ok = 0
        self.llm_rejected = 0

    def render(self, ins: dict, persona: str, lang: str = "en") -> dict:
        title = _render_frame(ins["headline"], lang, persona)
        lines = []
        for fr in ins["reasons"]:
            if persona not in fr["aud"]:
                continue
            lines.append({"text": _render_frame(fr, lang, persona), "ev": fr["ev"], "k": fr["k"]})
        if persona == "access":
            # put the spatial description first for audio users
            lines.sort(key=lambda r: r["k"] != "r.location")
        lines = lines[:MAX_LINES[persona]]
        lower = title if not lines else f"{title} · {lines[0]['text']}"
        out = {"title": title, "lines": lines, "lower_third": lower[:120], "lang": lang, "persona": persona,
               "source": "phrasebank"}
        if persona == "access":
            out["speech"] = ". ".join([title] + [l["text"] for l in lines]) + "."
        return out

    async def render_llm(self, ins: dict, persona: str, lang: str) -> Optional[dict]:
        """LLM polish / any-language rendering, verified before use."""
        if not self.llm.available:
            return None
        base = self.render(ins, persona, "en" if lang not in BANKS else lang)
        prompt = json.dumps({"persona": persona, "target_language": lang, "minute": ins["minute"],
                             "title": base["title"], "lines": [l["text"] for l in base["lines"]]}, ensure_ascii=False)
        for attempt in range(2):
            data = await self.llm.run_json("Narrator", NARRATOR_INSTRUCTIONS, prompt, timeout=5.0)
            if not data or "title" not in data:
                return None
            texts = [data["title"]] + list(data.get("lines", []))
            issues = self.checker.check_text(ins, texts)
            if not issues:
                self.llm_ok += 1
                lines = [{"text": t, "ev": base["lines"][i]["ev"] if i < len(base["lines"]) else ins["event_ids"],
                          "k": base["lines"][i]["k"] if i < len(base["lines"]) else "llm"}
                         for i, t in enumerate(data.get("lines", [])[:MAX_LINES[persona]])]
                out = {**base, "title": data["title"], "lines": lines, "lang": lang, "source": f"llm:{self.llm.backend}",
                       "lower_third": (data["title"] + (f" · {lines[0]['text']}" if lines else ""))[:120]}
                if persona == "access":
                    out["speech"] = ". ".join([out["title"]] + [l["text"] for l in lines]) + "."
                return out
            self.llm_rejected += 1
            self.checker.corrected += 1
            prompt += f"\nYour previous answer was rejected by the fact checker: {issues[:3]}. Fix it."
        return None
