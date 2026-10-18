"""Neural voice via Azure AI Speech (text to speech REST API).

Used for the audio-description mode and the voice-over on personal highlight reels.
Auth, first match wins:
  AZURE_SPEECH_KEY + AZURE_SPEECH_REGION                  subscription key
  AZURE_SPEECH_RESOURCE_ID + AZURE_SPEECH_REGION          Microsoft Entra ID (managed identity), no secrets
Without either, the browser's own speech synthesis is used and reels are captioned only.
"""
from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from typing import Optional
from xml.sax.saxutils import escape

log = logging.getLogger("touchline.speech")

VOICES = {
    "en": ("en-GB", "en-GB-RyanNeural"), "es": ("es-ES", "es-ES-AlvaroNeural"), "fr": ("fr-FR", "fr-FR-HenriNeural"),
    "pt": ("pt-PT", "pt-PT-DuarteNeural"), "de": ("de-DE", "de-DE-ConradNeural"), "ja": ("ja-JP", "ja-JP-KeitaNeural"),
    "hi": ("hi-IN", "hi-IN-MadhurNeural"), "ar": ("ar-SA", "ar-SA-HamedNeural"), "zh": ("zh-CN", "zh-CN-YunxiNeural"),
    "ta": ("ta-IN", "ta-IN-ValluvarNeural"), "sw": ("sw-KE", "sw-KE-RafikiNeural"),
}


# the co-commentator: a second, contrasting voice per language
VOICES_ANALYST = {
    "en": "en-GB-SoniaNeural", "es": "es-ES-ElviraNeural", "fr": "fr-FR-DeniseNeural", "pt": "pt-PT-RaquelNeural",
    "de": "de-DE-KatjaNeural", "ja": "ja-JP-NanamiNeural", "hi": "hi-IN-SwaraNeural", "ar": "ar-SA-ZariyahNeural",
    "zh": "zh-CN-XiaoxiaoNeural", "ta": "ta-IN-PallaviNeural", "sw": "sw-KE-ZuriNeural",
}


class Speech:
    def __init__(self) -> None:
        self.region = os.getenv("AZURE_SPEECH_REGION")
        self.key = os.getenv("AZURE_SPEECH_KEY")
        self.resource_id = os.getenv("AZURE_SPEECH_RESOURCE_ID")
        self._token: Optional[tuple[str, float]] = None
        self.cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self.calls = 0
        self.errors = 0

    @property
    def available(self) -> bool:
        return bool(self.region and (self.key or self.resource_id)) and os.getenv("TOUCHLINE_SPEECH", "on") != "off"

    def status(self) -> dict:
        return {"available": self.available, "mode": "key" if self.key else "entra" if self.resource_id else "browser",
                "calls": self.calls, "errors": self.errors}

    def _auth(self) -> dict:
        if self.key:
            return {"Ocp-Apim-Subscription-Key": self.key}
        if not self._token or self._token[1] < time.time() + 120:
            from azure.identity import DefaultAzureCredential

            tok = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
            self._token = (tok.token, tok.expires_on)
        return {"Authorization": f"Bearer aad#{self.resource_id}#{self._token[0]}"}

    @staticmethod
    def ssml(text: str, lang: str, who: str = "lead") -> str:
        locale, voice = VOICES.get(lang, VOICES["en"])
        if who == "analyst":
            voice = VOICES_ANALYST.get(lang, VOICES_ANALYST["en"]) if lang in VOICES else VOICES_ANALYST["en"]
        rate = "+12%" if who == "lead" else "+2%"
        return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
                f'<voice name="{voice}"><prosody rate="{rate}">{escape(text)}</prosody></voice></speak>')

    async def synthesize(self, text: str, lang: str = "en", who: str = "lead") -> Optional[bytes]:
        if not self.available or not text.strip():
            return None
        key = (lang, who, text)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        import httpx

        self.calls += 1
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                                      headers={**self._auth(), "Content-Type": "application/ssml+xml",
                                               "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                                               "User-Agent": "touchline"},
                                      content=self.ssml(text, lang, who).encode())
                r.raise_for_status()
                audio = r.content
        except Exception as exc:
            self.errors += 1
            log.warning("speech failed: %s", exc)
            return None
        self.cache[key] = audio
        while len(self.cache) > 300:
            self.cache.popitem(last=False)
        return audio


speech = Speech()
