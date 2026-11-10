"""run.py — OPT-IN live baseline run. NOT part of the default test suite.

Runs the whole solver-free corpus against whatever provider ``COPILOT_PROVIDER``
selects (default would be mock — pass hai for the real scoreboard) and prints it:

    COPILOT_PROVIDER=hai .venv/bin/python -m fleetpy_copilot.eval.run

This is the deliberate "observe" step: it makes real LLM calls. The default pytest
path never imports or triggers this; it uses MockProvider offline.
"""
from __future__ import annotations

import sys

from fleetpy_copilot.providers import make_provider

from .harness import run_harness


def main(argv=None) -> int:
    provider = make_provider()  # reads COPILOT_PROVIDER (mock|hai|openai|anthropic)
    board = run_harness(provider, do_dry_run=True)
    print(board.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
