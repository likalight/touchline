"""Evaluate the analyst agent with Microsoft Foundry evaluators plus Touchline's own checks.

    FOUNDRY_PROJECT_ENDPOINT=... FOUNDRY_MODEL=gpt-4.1-mini python scripts/foundry_eval.py

* Foundry built-in judges: relevance, coherence, task adherence, intent resolution, tool-call accuracy,
  tool-output use, and the hate/unfairness and violence safety evaluators
  (run in the Foundry project; the report link opens the results in the portal)
* Touchline checks, run locally on the same conversations:
  - grounded_numbers: every number in the answer appears in a tool result
  - cites_events: answers about specific moments cite an event ID
  - concise: three sentences or fewer, as the instructions require

Plays a full synthetic match first, so the agent's tools see real match state.
Writes docs/FOUNDRY_EVAL.md.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUERIES = [
    "Why did Kestrel Bay score in the 90th minute?",
    "How has the red card changed the match?",
    "Who is the best player on the pitch and why?",
    "Which team is pressing better, and how do you know?",
    "Explain the xG race.",
    "What has Kofi Varga done tonight?",
    "Is this match under control or chaotic right now?",
    "What happened between minutes 30 and 40?",
    "¿Por qué marcó Ironmoor en el minuto 36?",
    "Qui a été le meilleur gardien ?",
    "Who has run the fastest?",
    "What is the win probability now and what moved it most?",
]
NUM = re.compile(r"\d+(?:\.\d+)?")


def _get(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _texts(conversation) -> str:
    """Only tool outputs are evidence. Prompts and model responses cannot verify themselves."""
    out = []
    for m in conversation or []:
        role = str(_get(m, "role", "")).lower()
        for c in _get(m, "contents", []) or []:
            kind = str(_get(c, "type", "")).lower()
            if kind == "function_result" or role == "tool":
                v = _get(c, "result")
                if v is None:
                    v = _get(c, "text")
                if v is not None:
                    out.append(str(v))
        if role == "tool" and isinstance(_get(m, "content"), str):
            out.append(_get(m, "content"))
    return " ".join(out)


def grounded_numbers(query: str, response: str, conversation) -> dict:
    tools = _texts(conversation)
    corpus = set(NUM.findall(re.sub(r"\bE\d{5}\b", "", tools)))
    corpus |= {f"{float(n):g}" for n in corpus}
    nums = [n for n in NUM.findall(re.sub(r"\bE\d{5}\b", "", response))]
    bad = [n for n in nums if n not in corpus and f"{float(n):g}" not in corpus]
    ok = bool(tools) and not bad
    return {"passed": ok, "score": float(ok),
            "reason": "no tool evidence" if not tools else f"unsupported: {bad}" if bad else "numbers present in tool outputs (not semantic verification)"}


def cites_events(query: str, response: str, conversation=None) -> dict:
    needs = bool(re.search(r"\bwhy\b|por qué|pourquoi|happened|explain", query, re.I))
    cited = set(re.findall(r"E\d{5}", response))
    available = set(re.findall(r"E\d{5}", _texts(conversation)))
    ok = ((not needs) or bool(cited)) and cited <= available
    return {"passed": ok, "score": 1.0 if ok else 0.0}


def concise(response: str) -> bool:
    return len(re.findall(r"[.!?](\s|$)", response.strip())) <= 3


async def main() -> int:
    if not (os.getenv("FOUNDRY_PROJECT_ENDPOINT") and os.getenv("FOUNDRY_MODEL")):
        print("Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL (azd env get-values) to run the Foundry evaluation.")
        return 1
    os.environ.setdefault("TOUCHLINE_LLM", "on")
    os.environ.setdefault("TOUCHLINE_FOUNDRY_AGENTS", "on")
    from agent_framework import LocalEvaluator, evaluate_agent, evaluator
    from agent_framework.foundry import FoundryEvals

    from touchline.agents.ask import INSTRUCTIONS
    from touchline.llm import get_llm
    from touchline.runtime import MatchSession

    s = MatchSession(seed=87, speed=1000)
    s.control("jump", 200)
    s.start()
    while not s.done:
        await asyncio.sleep(0.05)
    llm = get_llm()
    agent = llm.agent("AskTheAnalyst", INSTRUCTIONS, s.ask_agent.tools())
    if not llm.hosted.get("AskTheAnalyst"):
        print("The published Foundry agent is required for this evaluation; local fallback is not cloud evidence.")
        return 1

    local = LocalEvaluator(evaluator(grounded_numbers, name="touchline_grounded_numbers"),
                           evaluator(cites_events, name="touchline_cites_events"), evaluator(concise, name="touchline_concise"))
    foundry = FoundryEvals(client=llm.client, evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE,
                                                          FoundryEvals.TASK_ADHERENCE, FoundryEvals.INTENT_RESOLUTION,
                                                          FoundryEvals.TOOL_CALL_ACCURACY, FoundryEvals.TOOL_OUTPUT_UTILIZATION,
                                                          FoundryEvals.HATE_UNFAIRNESS, FoundryEvals.VIOLENCE])
    results = await evaluate_agent(agent=agent, queries=QUERIES, evaluators=[foundry, local], eval_name="Touchline analyst")

    rows = []
    for r in results:
        for name, counts in (r.per_evaluator or {}).items():
            total = sum(counts.values()) or 1
            rows.append(f"| {r.provider} | {name} | {counts.get('passed', 0)} / {total} |")
        link = f"\n[Open in the Foundry portal]({r.report_url})\n" if r.report_url else ""
        rows.append(link) if link else None
    hosted = "Foundry Agent Service (published version)" if llm.hosted.get("AskTheAnalyst") else f"Agent Framework agent on {llm.backend}"
    md = f"""# Foundry evaluation: the analyst agent

`python scripts/foundry_eval.py` ran {len(QUERIES)} questions (English, Spanish, French) against the analyst
after a full synthetic match. Agent: {hosted}, model `{llm.model}`.

| Provider | Evaluator | Passed |
|---|---|---|
""" + "\n".join(x for x in rows if x and x.startswith("|")) + "\n" + "\n".join(x for x in rows if x and not x.startswith("|")) + """

Foundry's judges score quality (relevance, coherence, task adherence, intent), tool use, and safety. Touchline's own checks
confirm what matters on air: no number the tools did not return, citations for "why" questions, and short answers.
"""
    checks = [counts for r in results for counts in (r.per_evaluator or {}).values()]
    passed = bool(checks) and all(c.get("passed", 0) > 0 and not c.get("failed", 0) and not c.get("error", 0) for c in checks)
    md += f"\nEvaluation gate: {'PASSED' if passed else 'FAILED'}.\n"
    (ROOT / "docs" / "FOUNDRY_EVAL.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
