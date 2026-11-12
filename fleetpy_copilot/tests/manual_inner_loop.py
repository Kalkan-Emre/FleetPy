#!/usr/bin/env python3
"""Manual inner-loop runner — pick prompts from inputs.py and drive them through
generate_config with a real provider (default: hai).

Usage examples
--------------
# Run every prompt, print a one-line summary:
    .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop

# Run a single prompt by id:
    .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop ir-01

# Run all prompts tagged 'happy-path':
    .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop --tag happy-path

# Use a specific provider (mock|hai|openai|anthropic):
    COPILOT_PROVIDER=mock .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop
    COPILOT_PROVIDER=hai  .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop ir-01

# Skip the dry-run gate (faster, no FleetPy init):
    .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop --no-dry-run ir-01

# Show verbose trace events for each call:
    .venv/bin/python -m fleetpy_copilot.tests.manual_inner_loop --trace ir-01
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from typing import List

from fleetpy_copilot.generate import (
    DryRunFailed, GeneratedConfig, GenerationFailed, NeedsInput, generate_config,
)
from fleetpy_copilot.providers import make_provider
from fleetpy_copilot.trace import ConsoleTracer, NULL_TRACER

from fleetpy_copilot.tests.inputs import PROMPTS, by_id, by_tag


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_W = 80

def _hr(char: str = "─") -> str:
    return char * _W


def _wrap(text: str, indent: int = 2) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=_W - indent, initial_indent=prefix, subsequent_indent=prefix)


def _print_result(prompt_id: str, prompt_text: str, result) -> None:
    print(_hr())
    print(f"[{prompt_id}]")
    print(_wrap(prompt_text))
    print()

    if isinstance(result, GeneratedConfig):
        status = "GeneratedConfig" + (" + dry-run OK" if result.dry_run else "")
        print(f"  OUTCOME  : {status} ({result.attempts} attempt(s))")
        print(f"  PARAMS   : {len(result.config)}")
        # show a representative sample of the config
        sample = list(result.config.items())[:8]
        for k, v in sample:
            print(f"             {k} = {v!r}")
        if len(result.config) > 8:
            print(f"             … ({len(result.config) - 8} more)")

    elif isinstance(result, NeedsInput):
        print(f"  OUTCOME  : NeedsInput ({result.attempts} attempt(s))")
        slot_names = [s.name for s in result.slots]
        print(f"  SLOTS    : {', '.join(slot_names)}")
        if result.other_errors:
            print(f"  ERRORS   : {', '.join(result.other_errors.keys())}")

    elif isinstance(result, GenerationFailed):
        print(f"  OUTCOME  : GenerationFailed ({result.attempts} attempt(s))")
        v = result.validation
        if v:
            print(f"  SUMMARY  : {v.summary()}")

    elif isinstance(result, DryRunFailed):
        print(f"  OUTCOME  : DryRunFailed ({result.attempts} attempt(s))")
        print(f"  DRY-RUN  : {result.dry_run.error}")

    else:
        print(f"  OUTCOME  : {type(result).__name__} — {result!r}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual inner-loop runner — drive prompts through generate_config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage examples")[1] if "Usage examples" in __doc__ else "",
    )
    parser.add_argument(
        "ids",
        nargs="*",
        help="Prompt id(s) from inputs.py (e.g. ir-01 pool-02). Omit to run all.",
    )
    parser.add_argument(
        "--tag",
        metavar="TAG",
        help="Run only prompts with this tag (e.g. happy-path, ir).",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Skip the FleetPy dry-run gate (faster).",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print each trace event as it fires.",
    )
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=1,
        metavar="N",
        help="Repair budget passed to generate_config (default: 1).",
    )
    args = parser.parse_args(argv)

    # resolve prompt list
    if args.ids:
        try:
            prompts = [by_id(pid) for pid in args.ids]
        except KeyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            valid = [p["id"] for p in PROMPTS]
            print(f"Valid ids: {', '.join(valid)}", file=sys.stderr)
            return 2
    elif args.tag:
        prompts = by_tag(args.tag)
        if not prompts:
            print(f"ERROR: no prompts with tag={args.tag!r}", file=sys.stderr)
            all_tags = sorted({t for p in PROMPTS for t in p["tags"]})
            print(f"All tags: {', '.join(all_tags)}", file=sys.stderr)
            return 2
    else:
        prompts = PROMPTS

    provider = make_provider()
    tracer = ConsoleTracer() if args.trace else NULL_TRACER

    print(_hr("═"))
    print(f"  Provider : {type(provider).__name__}")
    print(f"  Dry-run  : {args.dry_run}")
    print(f"  Repairs  : {args.max_repairs}")
    print(f"  Prompts  : {len(prompts)}")
    print(_hr("═"))
    print()

    outcomes: dict[str, str] = {}
    for prompt in prompts:
        result = generate_config(
            prompt["text"],
            provider,
            do_dry_run=args.dry_run,
            max_repairs=args.max_repairs,
            tracer=tracer,
        )
        label = type(result).__name__
        outcomes[prompt["id"]] = label
        _print_result(prompt["id"], prompt["text"], result)

    # summary table
    print(_hr("═"))
    print("  SUMMARY")
    print(_hr())
    for pid, label in outcomes.items():
        print(f"  {pid:<20}  {label}")
    print(_hr("═"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
