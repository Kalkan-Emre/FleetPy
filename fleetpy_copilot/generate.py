"""generate.py — orchestration: NL prompt -> validated, runnable config.

The loop is deliberately thin and the oracle, not the model, is the authority:

    provider.generate(prompt)
      -> validate()                         (closed-vocab + value semantics)
         -> missing mandatory?  ASK, don't infer   -> NeedsInput
         -> other errors?       build correction   -> re-ask (bounded by max_repairs)
         -> clean?              dry_run functional gate -> GeneratedConfig

"Ask, don't infer" is the key stance for a simulation tool: a silently invented
fleet size or demand file would bias a study. Missing mandatory parameters are
surfaced as slots for the caller to fill (the Rasa-style slot-filling hook),
driven directly off ``validate.resolve_mandatory_params``. Invalid-but-present
values are a model mistake and are sent back as a correction instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from . import schema
from .dryrun import DryRunResult, dry_run_tmp
from .provider import GenerationCall, Provider
from .trace import NULL_TRACER, Tracer
from .validate import ValidationResult, validate


@dataclass
class Slot:
    """A mandatory parameter the model did not supply — a thing to ask for."""
    name: str
    doc: str = ""
    valid_values: List[str] = field(default_factory=list)  # non-empty for module params


@dataclass
class NeedsInput:
    """Terminal outcome: the request is under-specified. Ask for these slots.

    ``other_errors`` carries any *non*-missing-mandatory problems found in the same
    candidate (bad module values, out-of-range values, type errors) so they are
    surfaced now instead of hidden until the slots are filled — otherwise a user
    would fix the missing params, resubmit, and only then learn about a bad value.
    """
    slots: List[Slot]
    candidate: Dict[str, object]
    validation: ValidationResult
    other_errors: Dict[str, str] = field(default_factory=dict)


@dataclass
class GenerationFailed:
    """Terminal outcome: the model produced invalid output and the repair budget
    was exhausted without converging."""
    candidate: Dict[str, object]
    validation: ValidationResult
    attempts: int


@dataclass
class DryRunFailed:
    """Terminal outcome: the config validated clean but FleetPy could not load it
    (the functional gate failed at init). Distinct from GenerationFailed, which is
    a *validation* failure the model could repair."""
    config: Dict[str, object]
    validation: ValidationResult
    dry_run: DryRunResult
    attempts: int


@dataclass
class GeneratedConfig:
    """Terminal outcome: a validated config, dry-run verified when requested.

    Invariant: if ``dry_run`` is not ``None`` then ``dry_run.ok`` is ``True`` — a
    failed dry-run is returned as ``DryRunFailed``, never as a GeneratedConfig."""
    config: Dict[str, object]
    validation: ValidationResult
    dry_run: Optional[DryRunResult] = None
    attempts: int = 1


def _slots_for(missing: List[str]) -> List[Slot]:
    return [
        Slot(name=m, doc=schema.doc_for(m), valid_values=schema.valid_values_for(m))
        for m in sorted(missing)
    ]


def _correction_message(result: ValidationResult) -> str:
    """Turn a (non-missing-mandatory) validation failure into a correction prompt,
    grounding invalid module values in their real enum so the model can converge."""
    parts: List[str] = [result.summary()]
    for param, bad in result.invalid_module_values.items():
        valid = schema.valid_values_for(param)
        parts.append(f"'{bad}' is not a valid {param}; choose one of: {valid}")
    return " | ".join(parts)


def _provider_call(provider: Provider, prompt: str, correction: Optional[str]):
    """Call the provider, preferring ``generate_verbose`` (which also surfaces the
    rendered prompts + raw reply into the trace) when the provider implements it.

    Falls back to the plain ``generate`` contract with empty prompt fields, so any
    ``Provider`` works. Returns a ``GenerationCall``."""
    verbose = getattr(provider, "generate_verbose", None)
    if callable(verbose):
        return verbose(prompt, correction=correction)
    raw = provider.generate(prompt, correction=correction)
    return GenerationCall(config=raw)


def generate_config(
    prompt: str,
    provider: Provider,
    *,
    constant: Optional[Mapping[str, object]] = None,
    max_repairs: int = 1,
    do_dry_run: bool = True,
    tracer: Tracer = NULL_TRACER,
):
    """Drive the provider to a validated config, or a typed non-success outcome.

    ``constant`` is merged under each candidate (scenario overrides constant),
    mirroring FleetPy's own merge order. Returns one of ``GeneratedConfig`` /
    ``NeedsInput`` / ``GenerationFailed``.

    ``tracer`` is an optional observability seam (default no-op): when a real tracer
    is supplied, each step of the loop is emitted as a structured event. Instrumentation
    is purely observational — it never alters the candidate, the validator, or the
    outcome. See ``trace.py``.
    """
    base = dict(constant or {})
    correction: Optional[str] = None
    last: Optional[ValidationResult] = None
    last_candidate: Dict[str, object] = {}

    attempts = 0
    with tracer.span("generate"):
        # one initial attempt + up to max_repairs re-asks
        for _ in range(max_repairs + 1):
            attempts += 1
            tracer.emit(
                "attempt",
                attempt=attempts,
                message=f"{attempts}/{max_repairs + 1}",
                correction=correction,
            )
            call = _provider_call(provider, prompt, correction)
            raw = call.config
            if not isinstance(raw, Mapping):
                raise TypeError(
                    f"provider.generate must return a dict/mapping, got {type(raw).__name__}"
                )
            tracer.emit(
                "llm_call",
                attempt=attempts,
                message=f"{len(raw)} param(s)",
                candidate_keys=sorted(raw.keys()),
                system_prompt=call.system_prompt,
                user_prompt=call.user_prompt,
                raw_reply=call.raw_reply,
            )
            candidate = {**base, **raw}
            last_candidate = candidate
            tracer.emit(
                "merge",
                attempt=attempts,
                constant_keys=sorted(base.keys()),
                candidate_keys=sorted(candidate.keys()),
            )
            result = validate(candidate)
            last = result
            tracer.emit(
                "validate",
                attempt=attempts,
                message=result.summary(),
                ok=result.ok,
                unknown_params=list(result.unknown_params),
                invalid_module_values=dict(result.invalid_module_values),
                missing_mandatory=list(result.missing_mandatory),
                type_errors=dict(result.type_errors),
                value_errors=dict(result.value_errors),
            )

            if result.ok:
                dr = dry_run_tmp(base, candidate) if do_dry_run else None
                if dr is not None:
                    tracer.emit(
                        "dry_run", attempt=attempts, ok=dr.ok, error=dr.error,
                        message="ok" if dr.ok else "failed",
                    )
                if dr is not None and not dr.ok:
                    # validated clean but FleetPy could not initialize it -> gate fails.
                    tracer.emit(
                        "outcome", attempt=attempts,
                        type="DryRunFailed", attempts=attempts,
                    )
                    return DryRunFailed(
                        config=candidate, validation=result, dry_run=dr, attempts=attempts
                    )
                tracer.emit(
                    "outcome", attempt=attempts,
                    type="GeneratedConfig", attempts=attempts,
                )
                return GeneratedConfig(
                    config=candidate, validation=result, dry_run=dr, attempts=attempts
                )

            # under-specification is the user's to resolve, not the model's — ask.
            # Surface any OTHER errors in the same candidate too, so nothing is hidden.
            if result.missing_mandatory:
                other = {
                    **{p: f"invalid value {v!r}" for p, v in result.invalid_module_values.items()},
                    **result.value_errors,
                    **result.type_errors,
                }
                slots = _slots_for(result.missing_mandatory)
                tracer.emit(
                    "needs_input", attempt=attempts,
                    message=f"{len(slots)} slot(s)",
                    slots=[s.name for s in slots],
                    other_errors=other,
                )
                tracer.emit(
                    "outcome", attempt=attempts,
                    type="NeedsInput", attempts=attempts,
                )
                return NeedsInput(
                    slots=slots,
                    candidate=candidate,
                    validation=result,
                    other_errors=other,
                )

            # a model mistake (bad name/enum/value/type) -> send back for repair.
            correction = _correction_message(result)
            tracer.emit("repair", attempt=attempts, correction=correction)

        tracer.emit("outcome", type="GenerationFailed", attempts=attempts)
        return GenerationFailed(candidate=last_candidate, validation=last, attempts=attempts)
