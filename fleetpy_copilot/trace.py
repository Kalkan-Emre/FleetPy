"""trace.py — the copilot's cross-cutting observability seam.

Loop code emits named step events through a one-method ``Tracer``; how those events
are rendered (indented console text, a JSON file, an API-response array) is decoupled
from where they are emitted. This mirrors the ``Provider`` seam in ``provider.py``: a
tiny protocol with a no-op default, so instrumentation is additive and the same event
stream feeds every renderer.

The key design property is **structural nesting**: an emit site names only its own
step; the tracer stamps the current ``span`` stack onto the event. Wrapping a loop in
one more ``span(...)`` adds one path element (and one console indent) with no change to
the inner emit sites — which is how the M2.3 outer conversation loop will plug in
without changing the inner loop or the user-facing trace style.

Nothing here imports the rest of the package; the provider must never import this
module (full prompt/reply reach the trace via data the loop already holds — see
``generate.py`` and ``GenerationCall`` in ``provider.py``).
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import IO, Dict, Iterator, List, Mapping, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Event:
    """One unit crossing the seam.

    ``payload`` is a JSON-serializable mapping (the structured step data) and is the
    single source for both the human line and the JSON object — there is no second
    model. ``span`` is the ordered nesting path at emit time; ``seq`` is assigned by
    the tracer and strictly increases within a request so order can be reconstructed
    independent of transport.
    """

    step: str
    span: tuple = ()
    seq: int = 0
    attempt: Optional[int] = None
    payload: Mapping[str, object] = field(default_factory=dict)
    message: str = ""

    def to_json(self) -> Dict[str, object]:
        """Render as a JSON-able dict (``default=str`` safety net applied at dump time)."""
        return {
            "seq": self.seq,
            "step": self.step,
            "span": list(self.span),
            "attempt": self.attempt,
            "message": self.message,
            "payload": dict(self.payload),
        }


@runtime_checkable
class Tracer(Protocol):
    """The observability seam. One method; emit sites name only their own step.

    The tracer assigns ``seq`` and stamps the current span path — callers pass only
    ``step``/``attempt``/``message``/``payload``. ``span`` is a context manager that
    pushes/pops a nesting name.
    """

    def emit(
        self,
        step: str,
        *,
        attempt: Optional[int] = None,
        message: str = "",
        **payload: object,
    ) -> None:
        ...

    def span(self, name: str): ...


class _BaseTracer:
    """Shared span-stack + seq bookkeeping; subclasses implement ``_handle(event)``."""

    def __init__(self) -> None:
        self._span: List[str] = []
        self._seq: int = 0

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        self._span.append(name)
        try:
            yield
        finally:
            # pop on normal exit AND on exception unwind, so the stack stays balanced
            self._span.pop()

    def emit(
        self,
        step: str,
        *,
        attempt: Optional[int] = None,
        message: str = "",
        **payload: object,
    ) -> None:
        event = Event(
            step=step,
            span=tuple(self._span),
            seq=self._seq,
            attempt=attempt,
            payload=payload,
            message=message,
        )
        self._seq += 1
        self._handle(event)

    def _handle(self, event: Event) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class _NullTracer(_BaseTracer):
    """No-op tracer: the default for ``generate_config`` so existing behavior is
    byte-for-byte unchanged. Emitting does nothing and costs nothing observable."""

    def emit(self, step, *, attempt=None, message="", **payload) -> None:
        return None

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        yield


#: Module singleton no-op tracer. Use this as the default everywhere.
NULL_TRACER: Tracer = _NullTracer()


class CollectingTracer(_BaseTracer):
    """Retains every ``Event`` in ``self.events`` — the substrate for test assertions
    and for serializing a request's trace into an API response body."""

    def __init__(self) -> None:
        super().__init__()
        self.events: List[Event] = []

    def _handle(self, event: Event) -> None:
        self.events.append(event)


class ConsoleTracer(_BaseTracer):
    """One indented human line per event (indent = span depth), written to a stream
    (stderr by default, so stdout stays clean if piped). Full multi-line payload
    fields (prompts, replies) are printed as indented blocks under the step line."""

    #: payload keys rendered as full indented blocks rather than inline key=value
    _BLOCK_KEYS = ("system_prompt", "user_prompt", "raw_reply", "correction")

    def __init__(self, stream: Optional[IO[str]] = None) -> None:
        super().__init__()
        self._stream = stream if stream is not None else sys.stderr

    def _handle(self, event: Event) -> None:
        indent = "  " * len(event.span)
        head = f"{indent}{event.step}"
        if event.attempt is not None:
            head += f" [attempt {event.attempt}]"
        if event.message:
            head += f"  {event.message}"
        inline = {
            k: v for k, v in event.payload.items()
            if k not in self._BLOCK_KEYS and v is not None
        }
        if inline:
            head += "  " + " ".join(f"{k}={_short(v)}" for k, v in inline.items())
        print(head, file=self._stream)
        for key in self._BLOCK_KEYS:
            val = event.payload.get(key)
            if val:
                print(f"{indent}  {key}:", file=self._stream)
                for line in str(val).splitlines():
                    print(f"{indent}    {line}", file=self._stream)
        self._stream.flush()


class JsonFileTracer(CollectingTracer):
    """Collects events and writes the request's full event array to one self-contained
    JSON file, ``<dir>/req-<request_id>.json``, when the request's outermost span exits.

    One file per request keeps each trace isolated and easy to inspect. This is a
    DIFFERENT artifact from the planned day-one data-collection JSONL (which logs
    NL→config *pairs*, not step traces)."""

    def __init__(self, directory: str, *, request_id: Optional[str] = None) -> None:
        super().__init__()
        self._dir = directory
        self._request_id = request_id or "trace"
        self._written = False

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        with super().span(name):
            yield
        # when the outermost span unwinds, the stack is empty -> flush the file once
        if not self._span and not self._written:
            self._flush()

    def _flush(self) -> None:
        self._written = True
        os.makedirs(self._dir, exist_ok=True)
        path = os.path.join(self._dir, f"req-{self._request_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([e.to_json() for e in self.events], fh, default=str, indent=2)
        self.path = path


class CompositeTracer(_BaseTracer):
    """Fans one emit out to several tracers in a single pass. Owns the authoritative
    span stack + seq; children receive fully-formed events via ``_emit_event`` so every
    renderer sees the same span path and ordering. Span enter/exit is ALSO propagated to
    children so span-driven children (e.g. ``JsonFileTracer`` flushing on outermost exit)
    behave as if they tracked the stack themselves."""

    def __init__(self, tracers: List[Tracer]) -> None:
        super().__init__()
        self._tracers = list(tracers)

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        self._span.append(name)
        ctxs = [t.span(name) for t in self._tracers]
        for c in ctxs:
            c.__enter__()
        try:
            yield
        finally:
            self._span.pop()
            for c in reversed(ctxs):
                c.__exit__(None, None, None)

    def _handle(self, event: Event) -> None:
        for t in self._tracers:
            # children are _BaseTracer instances in practice; hand them the event directly
            handler = getattr(t, "_emit_event", None)
            if handler is not None:
                handler(event)
            else:  # pragma: no cover - defensive for exotic tracers
                t.emit(
                    event.step,
                    attempt=event.attempt,
                    message=event.message,
                    **dict(event.payload),
                )


def _emit_event(self: _BaseTracer, event: Event) -> None:
    """Accept a pre-formed event from a CompositeTracer (preserves span/seq)."""
    self._handle(event)


# give the collecting/console tracers a way to accept composite-formed events
_BaseTracer._emit_event = _emit_event  # type: ignore[attr-defined]


def _short(value: object, limit: int = 80) -> str:
    """Compact one-line rendering of an inline payload value for the console."""
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, default=str)
    else:
        text = str(value)
    text = text.replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text
