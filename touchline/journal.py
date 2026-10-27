"""Single-partition input journal: state history and resume offset commit together.

Replaying a checkpoint without its match history loses state. This small, single-writer
prototype stores both in one atomic blob replacement. It is not a multi-replica state store.
"""
from __future__ import annotations

import copy
import json


class InputJournal:
    def __init__(self, store, source: dict, batch_size: int = 32):
        self.store, self.source, self.batch_size = store, source, batch_size
        self.document = {"schema": "touchline.journal/1", "source": source,
                         "meta": None, "events": [], "offset": None}
        self.dirty = 0
        self.completed_match_id = None

    async def restore(self) -> dict:
        self.completed_match_id = None
        saved = await self.store.read()
        if saved is not None:
            if saved.get("schema") != "touchline.journal/1" or saved.get("source") != self.source:
                raise ValueError("Journal source does not match this consumer; refusing an unsafe resume")
            if not saved.get("meta") or not isinstance(saved.get("events"), list):
                raise ValueError("Journal is incomplete; refusing to skip match history")
            self.document = saved
        return copy.deepcopy(self.document)

    async def append(self, payload: dict, offset: str):
        if "meta" in payload:
            prior = self.document["meta"]
            if prior and self.completed_match_id != prior["match_id"]:
                raise ValueError("Previous match processing is not acknowledged; refusing to discard replay history")
            # Metadata replaces the only retained history. Commit the replacement
            # atomically, and leave both in-memory and stored history intact on failure.
            updated = {**self.document, "meta": copy.deepcopy(payload["meta"]), "events": [], "offset": offset}
            await self.store.write(updated)
            self.document, self.dirty, self.completed_match_id = updated, 0, None
            return
        else:
            meta = self.document["meta"]
            if meta is None:
                raise ValueError("Feed must begin with match metadata; retained history may have expired")
            if payload.get("match_id") and payload["match_id"] != meta["match_id"]:
                raise ValueError("One journal partition supports one active match; interleaved matches are not supported")
            if len(self.document["events"]) >= 10000:
                raise ValueError("Match journal limit exceeded")
            self.document["events"].append(payload)
        self.document["offset"] = offset
        self.dirty += 1
        if self.dirty >= self.batch_size or "meta" in payload or payload.get("type") == "full_time":
            await self.flush()

    def acknowledge_match(self, match_id: str):
        """Called only after processing and all durable output acceptance finish.

        This signal is deliberately not restored: after a restart, replay and the
        outbox ledger establish completion again before old history can be retired.
        """
        if not self.document["meta"] or self.document["meta"]["match_id"] != match_id:
            raise ValueError("Cannot acknowledge a different input match")
        self.completed_match_id = match_id

    async def flush(self):
        if self.dirty:
            await self.store.write(copy.deepcopy(self.document))
            self.dirty = 0


class BlobJournalStore:
    def __init__(self, url, credential):
        from azure.storage.blob.aio import BlobClient
        self.client = BlobClient.from_blob_url(url, credential=credential)
        self.etag = None

    async def read(self):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            download = await self.client.download_blob()
            data = await download.readall()
            self.etag = download.properties.etag
            return json.loads(data)
        except ResourceNotFoundError:
            return None

    async def write(self, value):
        from azure.storage.blob import ContentSettings
        from azure.core import MatchConditions
        options = {"overwrite": False} if self.etag is None else {
            "overwrite": True, "etag": self.etag, "match_condition": MatchConditions.IfNotModified}
        result = await self.client.upload_blob(json.dumps(value, separators=(",", ":")), **options,
                                               content_settings=ContentSettings(content_type="application/json"))
        self.etag = result["etag"]

    async def close(self):
        await self.client.close()
