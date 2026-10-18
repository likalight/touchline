"""Azure AI Content Safety for everything a language model writes and everything a fan types.

* Fan questions go through **Prompt Shields** (jailbreak / prompt-injection detection) and text
  moderation before any agent sees them.
* Language-model output (any-language narration, analyst answers) is moderated after the
  FactChecker passes it; anything at or above the severity threshold falls back to verified
  phrase-bank copy.

Auth is Microsoft Entra ID (the app's managed identity, role "Cognitive Services User").
Without an endpoint, a small local screen (injection patterns, links, length) stands in, and the
Foundry agents keep their own Responsible-AI content policy.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import OrderedDict
from typing import Optional

log = logging.getLogger("touchline.safety")
API = "2024-09-01"
INJECTION = re.compile(r"ignore (all |any |the )?(previous|prior|above) (instructions|rules)|system prompt|developer mode|"
                       r"you are now|jailbreak|disregard (your|the) (rules|instructions)|act as (an? )?(unfiltered|dan)\b", re.I)


class ContentSafety:
    def __init__(self) -> None:
        self.endpoint = (os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT") or "").rstrip("/")
        self.key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
        self.threshold = int(os.getenv("TOUCHLINE_SAFETY_THRESHOLD", "4"))  # 0, 2, 4, 6: block at or above
        self._token: Optional[tuple[str, float]] = None
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.stats = {"checked": 0, "blocked": 0, "shield_attacks": 0, "errors": 0}

    @property
    def mode(self) -> str:
        return "azure" if self.endpoint and os.getenv("TOUCHLINE_SAFETY", "on") != "off" else "local"

    def status(self) -> dict:
        return {"mode": self.mode, "threshold": self.threshold, **self.stats}

    def _headers(self) -> dict:
        if self.key:
            return {"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/json"}
        if not self._token or self._token[1] < time.time() + 120:
            from azure.identity import DefaultAzureCredential

            tok = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
            self._token = (tok.token, tok.expires_on)
        return {"Authorization": f"Bearer {self._token[0]}", "Content-Type": "application/json"}

    async def _post(self, path: str, body: dict) -> Optional[dict]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=4) as c:
                r = await c.post(f"{self.endpoint}/contentsafety/{path}?api-version={API}", headers=self._headers(), json=body)
                r.raise_for_status()
                return r.json()
        except Exception as exc:  # pragma: no cover - depends on Azure
            self.stats["errors"] += 1
            log.warning("content safety call failed: %s", exc)
            return None

    async def moderate(self, text: str) -> dict:
        """{'ok': bool, 'categories': {...}, 'source': 'azure'|'local'}"""
        self.stats["checked"] += 1
        if text in self.cache:
            return self.cache[text]
        out = {"ok": True, "categories": {}, "source": "local"}
        if self.mode == "azure":
            res = await self._post("text:analyze", {"text": text[:10000], "outputType": "FourSeverityLevels"})
            if res is not None:
                cats = {c["category"]: c.get("severity", 0) for c in res.get("categoriesAnalysis", [])}
                out = {"ok": all(v < self.threshold for v in cats.values()), "categories": cats, "source": "azure"}
        if not out["ok"]:
            self.stats["blocked"] += 1
        self.cache[text] = out
        if len(self.cache) > 2000:
            self.cache.popitem(last=False)
        return out

    async def shield(self, user_prompt: str) -> dict:
        """Prompt Shields: is this fan question trying to take over the agent?"""
        local = bool(INJECTION.search(user_prompt)) or len(user_prompt) > 500 or "http" in user_prompt.lower()
        out = {"attack": local, "source": "local"}
        if self.mode == "azure":
            res = await self._post("text:shieldPrompt", {"userPrompt": user_prompt[:10000], "documents": []})
            if res is not None:
                out = {"attack": bool(res.get("userPromptAnalysis", {}).get("attackDetected")) or local, "source": "azure"}
        if out["attack"]:
            self.stats["shield_attacks"] += 1
        return out

    async def screen_question(self, q: str) -> Optional[str]:
        """None if the question can go to the analyst, else the reason it was refused."""
        if (await self.shield(q))["attack"]:
            return "prompt_attack"
        if not (await self.moderate(q))["ok"]:
            return "harmful_content"
        return None


safety = ContentSafety()
