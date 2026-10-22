"""SSE frame serialization and stream iteration."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import Request

from yggdrasil.connection_manager import ConnectionManager
from yggdrasil.models import RealmSummary
from yggdrasil.sse.poller import RealmPoller

REALM_SUMMARY_EVENT = "realm.summary"
DISCONNECT_CHECK_INTERVAL_SECONDS = 1.0


def format_sse(summary: RealmSummary) -> str:
    """Serialize a realm summary as a named SSE frame."""
    payload = json.dumps(summary.model_dump(mode="json"), sort_keys=True)
    return f"event: {REALM_SUMMARY_EVENT}\ndata: {payload}\n\n"


async def stream_realm_summary(
    request: Request,
    realm_id: str,
    connection_manager: ConnectionManager,
    poller: RealmPoller,
    queue: asyncio.Queue[RealmSummary],
) -> AsyncGenerator[str, None]:
    """Yield an initial summary followed by changed summaries until disconnect."""
    try:
        summary = poller.summary_for(realm_id)
        if summary is None:
            return
        yield format_sse(summary)

        while not await request.is_disconnected():
            try:
                summary = await asyncio.wait_for(queue.get(), DISCONNECT_CHECK_INTERVAL_SECONDS)
            except TimeoutError:
                continue
            yield format_sse(summary)
    finally:
        connection_manager.disconnect(realm_id, queue)
