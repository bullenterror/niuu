"""Surviving a model gateway that restarts under an open request.

Ravn's model calls go through Bifröst. When the platform rolls, the gateway pod
that holds a streamed answer is stopped, and the connection ends mid-body
(``httpx.RemoteProtocolError: peer closed connection without sending complete
message body``). The retry that guards the *connection* phase cannot help: the
request was accepted and half answered. Without a resume the whole task fails
and its operator messages or commission are lost, though the next request to
the replacement pod would have worked.

:func:`resumable_stream` re-issues the same request when the stream drops, and
tells the consumer to throw away the partial answer with a
``StreamEventType.STREAM_RESTART`` event. A model does not repeat itself word for
word, so a partial answer cannot be continued or de-duplicated, only replaced.

What bounds it is how long the gateway takes to come back: a wall-clock window
(``llm.stream_resume_window_seconds``), not an attempt count that stops covering
a rollout when the backoff changes. The window is the time one call may spend
*failing*: from each failure until a re-issued stream delivers its first event.
A stream that then runs for ten minutes does not use the window up, and one that
is cut again straight after delivering a few events does, so a gateway that
flaps cannot keep a call alive forever. When the window runs out the call raises
an ``LLMError`` naming the knob, and the exhaustion is counted on ``ravn.cap.hits``.

Only transient failures are resumed: a transport error, or a status that says
the server was unavailable (:data:`RETRYABLE_STATUS_CODES`). A 4xx other than
429, a stream the provider ended as truncated, and a malformed answer are
deterministic; repeating the request would give the same result, so they raise.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import NoReturn

import httpx

from ravn.cap_telemetry import record_cap_hit, record_retry
from ravn.domain.exceptions import LLMError
from ravn.domain.models import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)

#: The knob that bounds a resumed stream; named in every message about it.
STREAM_RESUME_KNOB = "llm.stream_resume_window_seconds"
#: The knob that bounds the retries of getting a first response header.
MAX_RETRIES_KNOB = "llm.max_retries"

#: Statuses that mean the server could not take the request right now. 429 asks
#: the caller to come back; 500/502/503/504 are what a gateway or its upstream
#: answers while it is restarting or overloaded.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class TransientStatusError(Exception):
    """A response whose status says the server was unavailable (retry later)."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def describe_failure(exc: BaseException) -> str:
    """One-line cause of a transient failure, for logs and error messages."""
    if isinstance(exc, TransientStatusError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def resumable_stream(
    *,
    provider: str,
    window_seconds: float,
    base_delay: float,
    max_backoff_seconds: float,
    open_response: Callable[[bool], Awaitable[httpx.Response]],
    read_events: Callable[[httpx.Response], AsyncIterator[StreamEvent]],
) -> AsyncIterator[StreamEvent]:
    """Yield the events of one model call, re-issuing it when the stream drops.

    *open_response* returns the open streaming response; its argument is
    ``True`` when the request is being re-issued after a failure. It raises
    ``httpx.TransportError`` or :class:`TransientStatusError` when the server
    cannot be reached or says it is unavailable. *read_events* parses one
    response into events and raises ``LLMError`` for a deterministic failure.

    A failure waits ``base_delay * 2**n`` seconds (``n`` counts the re-issues
    since the stream last delivered anything), capped at *max_backoff_seconds*
    and never past the end of the window, then tries again. When anything was already yielded
    from the failed attempt a ``STREAM_RESTART`` event is yielded first.

    Raises:
        LLMError: The window ran out (or is 0), naming ``llm.stream_resume_window_seconds``.
    """
    path = f"llm.{provider}.stream"
    down_since: float | None = None  # when the current run of failures began
    downtime = 0.0  # time spent failing in earlier runs of this call
    attempts = 0
    resumed = False
    delivered = False  # events yielded to the consumer since the last (re)start
    while True:
        response: httpx.Response | None = None
        failure: BaseException | None = None
        try:
            response = await open_response(resumed)
            async for event in read_events(response):
                if down_since is not None:
                    outage = time.monotonic() - down_since
                    downtime += outage
                    logger.info(
                        "%s: model stream resumed after %d re-issue(s) in %.1fs",
                        path,
                        attempts,
                        outage,
                    )
                    down_since = None
                    attempts = 0
                delivered = True
                yield event
            return
        except (httpx.TransportError, TransientStatusError) as exc:
            failure = exc
        finally:
            if response is not None:
                await response.aclose()

        # The consumer is told before the backoff, so it stops showing a
        # partial answer that is not going to be completed.
        if delivered:
            yield StreamEvent(type=StreamEventType.STREAM_RESTART)
            delivered = False
        now = time.monotonic()
        if down_since is None:
            down_since = now
        elapsed = downtime + (now - down_since)
        remaining = window_seconds - elapsed
        if remaining <= 0:
            _raise_exhausted(
                provider=provider,
                window_seconds=window_seconds,
                elapsed=elapsed,
                attempts=attempts,
                failure=failure,
            )
        delay = min(base_delay * (2**attempts), max_backoff_seconds, remaining)
        attempts += 1
        record_retry(
            path,
            f"{provider} model call interrupted ({describe_failure(failure)}); re-issuing the "
            f"request in {delay:.1f}s (re-issue {attempts}, {elapsed:.1f}s into the "
            f"{window_seconds:g}s {STREAM_RESUME_KNOB} window)",
        )
        await asyncio.sleep(delay)
        resumed = True


def _raise_exhausted(
    *,
    provider: str,
    window_seconds: float,
    elapsed: float,
    attempts: int,
    failure: BaseException | None,
) -> NoReturn:
    cause = describe_failure(failure) if failure is not None else "unknown"
    if window_seconds <= 0:
        message = (
            f"{provider} model stream was cut ({cause}) and {STREAM_RESUME_KNOB}=0 disables "
            f"re-issuing it; set {STREAM_RESUME_KNOB} to the longest gateway restart to survive"
        )
    else:
        message = (
            f"{provider} model stream was cut ({cause}) and could not be re-issued within "
            f"{STREAM_RESUME_KNOB}={window_seconds:g}s ({attempts} re-issue(s), {elapsed:.1f}s "
            "spent failing); the gateway or provider has been unreachable for "
            f"longer than the window. Check it, or raise {STREAM_RESUME_KNOB} to outlast "
            "the restart"
        )
    record_cap_hit(STREAM_RESUME_KNOB, message)
    status = failure.status_code if isinstance(failure, TransientStatusError) else None
    raise LLMError(message, status_code=status) from failure


async def reissue_request(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """POST *payload* once more and return the open streaming response.

    *headers* replace the client's defaults when given: a re-issue minutes after
    the first request must carry a freshly minted credential, not the one the
    client was created with.

    For re-issuing a request whose stream was cut: a single attempt, because the
    caller's window (not a count) decides how long to keep trying. A transport
    error propagates; a status in :data:`RETRYABLE_STATUS_CODES` raises
    :class:`TransientStatusError`. Any other status is returned for the caller
    to treat as the answer it is.
    """
    request = client.build_request("POST", url, json=payload, headers=headers)
    response = await client.send(request, stream=True)
    if response.status_code not in RETRYABLE_STATUS_CODES:
        return response
    await response.aclose()
    raise TransientStatusError(response.status_code)


def note_connection_retry(
    *,
    provider: str,
    failure: BaseException,
    delay: float,
    attempt: int,
    max_retries: int,
) -> None:
    """Log and count one retry of getting a response header (``llm.max_retries``)."""
    record_retry(
        f"llm.{provider}.connect",
        f"{provider} request failed ({describe_failure(failure)}); retrying in {delay:.1f}s "
        f"(attempt {attempt}/{max_retries}, {MAX_RETRIES_KNOB})",
    )


def connection_retries_exhausted(
    *, provider: str, max_retries: int, detail: str = "", status_code: int | None = None
) -> LLMError:
    """The error for a response header that never arrived; counts the cap hit.

    The caller raises it ``from`` the last failure.
    """
    message = (
        f"{provider} failed after {max_retries} retries{detail}; the gateway or provider is "
        f"unavailable. Raise {MAX_RETRIES_KNOB} (and llm.retry_base_delay) to ride out a "
        "longer outage"
    )
    record_cap_hit(MAX_RETRIES_KNOB, message)
    return LLMError(message, status_code=status_code)
