"""LLM backends, all routed through Microsoft Agent Framework `Agent`s.

Backend is chosen from the environment (first match wins):

  FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL     -> agent_framework.foundry.FoundryChatClient (Entra ID)
  AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_MODEL   -> OpenAIChatCompletionClient on the Azure OpenAI v1 API
                                                  (AZURE_OPENAI_API_KEY, or managed identity when absent)
  OPENAI_API_KEY (+ OPENAI_BASE_URL)           -> any OpenAI-compatible endpoint (e.g. Foundry Local)
  none / TOUCHLINE_LLM=off                     -> offline: deterministic phrase banks only

Every call is wrapped in a timeout and a circuit breaker: three consecutive failures open
the breaker for 60 s and the pipeline falls back to deterministic rendering, so the live
show never waits on a model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Optional

log = logging.getLogger("touchline.llm")


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.failures = 0
        self.opened_at: Optional[float] = None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at > self.cooldown:
            self.opened_at, self.failures = None, 0  # half-open: allow a retry
            return False
        return True

    def force_open(self, seconds: float) -> None:
        """Resilience drill: treat the model as down for `seconds`."""
        self.opened_at = time.monotonic() - self.cooldown + seconds

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


def _json_from(text: str) -> Any:
    text = text.strip()
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON in model output")
    return json.loads(m.group(0))


class LLM:
    def __init__(self) -> None:
        self.backend = "offline"
        self.model = None
        self.client = None
        self.breaker = CircuitBreaker()
        self.calls = 0
        self.errors = 0
        self.total_ms = 0.0
        self._agents: dict[str, Any] = {}
        self.hosted: dict[str, bool] = {}
        self.fallbacks = 0
        self._execution = ContextVar("touchline_execution", default=None)
        if os.getenv("TOUCHLINE_LLM", "").lower() in ("off", "offline", "0"):
            return
        try:
            self._init_client()
        except Exception as exc:  # pragma: no cover - depends on env
            log.warning("LLM backend unavailable, running offline: %s", exc)
            self.backend, self.client = "offline", None

    def _init_client(self) -> None:
        if os.getenv("FOUNDRY_PROJECT_ENDPOINT") and os.getenv("FOUNDRY_MODEL"):
            from agent_framework.foundry import FoundryChatClient
            from azure.identity import DefaultAzureCredential

            self.client = FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                                           model=os.environ["FOUNDRY_MODEL"], credential=DefaultAzureCredential())
            self.backend, self.model = "foundry", os.environ["FOUNDRY_MODEL"]
        elif os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_MODEL"):
            from agent_framework.openai import OpenAIChatCompletionClient

            base = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/"
            model = os.environ["AZURE_OPENAI_MODEL"]
            if os.getenv("AZURE_OPENAI_API_KEY"):
                self.client = OpenAIChatCompletionClient(model=model, base_url=base, api_key=os.environ["AZURE_OPENAI_API_KEY"])
            else:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider

                tp = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
                self.client = OpenAIChatCompletionClient(model=model, base_url=base, api_key=tp)
            self.backend, self.model = "azure_openai", model
        elif os.getenv("OPENAI_API_KEY"):
            from agent_framework.openai import OpenAIChatCompletionClient

            model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            self.client = OpenAIChatCompletionClient(model=model, base_url=os.getenv("OPENAI_BASE_URL"),
                                                     api_key=os.environ["OPENAI_API_KEY"])
            self.backend, self.model = "openai_compatible", model

    @property
    def available(self) -> bool:
        return self.client is not None and not self.breaker.open

    def agent(self, name: str, instructions: str, tools: Optional[list[Callable]] = None):
        """Cache stateless narrators only; tool closures belong to one request/match."""
        if self.client is None:
            return None
        if tools is not None or name not in self._agents:
            from agent_framework import Agent

            from touchline.foundry_agents import hosted_agent

            hosted = hosted_agent(name, tools) if self.backend == "foundry" else None
            agent = hosted or Agent(self.client, instructions, name=name, tools=tools,
                                   middleware=purview_middleware() or None)
            self.hosted[name] = hosted is not None
            if tools is not None:
                return agent
            self._agents[name] = agent
        return self._agents[name]

    async def run(self, name: str, instructions: str, prompt: str, timeout: float = 6.0,
                  tools: Optional[list[Callable]] = None) -> Optional[str]:
        evidence = {"request_id": uuid.uuid4().hex, "agent": name, "backend": self.backend,
                    "model": self.model, "path": "unavailable", "completed": False, "fallback": False}
        self._execution.set(evidence)
        if not self.available:
            return None
        agent = self.agent(name, instructions, tools)
        is_hosted = self.hosted.get(name, False)  # request-local: another request may update status
        evidence["path"] = "foundry_hosted" if is_hosted else "local_agent"
        t0 = time.perf_counter()
        self.calls += 1
        try:
            resp = await asyncio.wait_for(agent.run(prompt), timeout=timeout)
            self.breaker.ok()
            evidence["completed"] = True
            return resp.text
        except Exception as exc:
            self.errors += 1
            log.warning("agent %s failed: %s", name, exc)
            if is_hosted:
                # the published Foundry agent is unreachable: fall back to the same agent run locally, once
                from agent_framework import Agent

                fallback = Agent(self.client, instructions, name=name, tools=tools or None)
                self.hosted[name] = False
                self.fallbacks += 1
                evidence.update(path="local_agent", fallback=True)
                try:
                    resp = await asyncio.wait_for(fallback.run(prompt), timeout=timeout)
                    self.breaker.ok()
                    evidence["completed"] = True
                    return resp.text
                except Exception as fallback_exc:
                    self.errors += 1
                    log.warning("local agent %s failed: %s", name, fallback_exc)
            self.breaker.fail()
            return None
        finally:
            evidence["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            self.total_ms += evidence["duration_ms"]

    def execution(self) -> dict:
        """Provenance of this task's call, never another concurrent request's status."""
        return dict(self._execution.get() or {})

    async def run_json(self, name: str, instructions: str, prompt: str, timeout: float = 6.0) -> Optional[Any]:
        text = await self.run(name, instructions, prompt, timeout)
        if text is None:
            return None
        try:
            return _json_from(text)
        except Exception:
            self.breaker.fail()
            return None

    def status(self) -> dict:
        return {"backend": self.backend, "model": self.model, "breaker_open": self.breaker.open,
                "calls": self.calls, "errors": self.errors, "hosted_agents": [k for k, v in self.hosted.items() if v], "hosted_fallbacks": self.fallbacks,
                "avg_ms": round(self.total_ms / self.calls, 1) if self.calls else None}


class SessionLLM:
    """Session-local outage drills over a shared model client and real service breaker."""
    def __init__(self, shared):
        self.shared = shared
        self.breaker = CircuitBreaker()

    def __getattr__(self, name):
        return getattr(self.shared, name)

    @property
    def available(self):
        return not self.breaker.open and self.shared.available

    async def run(self, *args, **kwargs):
        return await self.shared.run(*args, **kwargs) if self.available else None

    async def run_json(self, *args, **kwargs):
        return await self.shared.run_json(*args, **kwargs) if self.available else None

    def status(self):
        return {**self.shared.status(), "breaker_open": self.breaker.open or self.shared.breaker.open,
                "session_outage_drill": self.breaker.open}


_LLM: Optional[LLM] = None


def purview_middleware() -> list:
    """Microsoft Purview data-security policies on agent prompts and responses (TOUCHLINE_PURVIEW=on)."""
    if os.getenv("TOUCHLINE_PURVIEW", "").lower() != "on":
        return []
    try:
        from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
        from azure.identity import DefaultAzureCredential

        return [PurviewPolicyMiddleware(DefaultAzureCredential(), PurviewSettings(app_name="Touchline"))]
    except Exception as exc:  # pragma: no cover - depends on tenant setup
        log.warning("Purview middleware unavailable: %s", exc)
        return []


def get_llm() -> LLM:
    global _LLM
    if _LLM is None:
        _LLM = LLM()
    return _LLM


def reset_llm() -> None:
    global _LLM
    _LLM = None
