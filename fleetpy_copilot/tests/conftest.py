"""Make both ``fleetpy_copilot`` and FleetPy's ``src`` importable regardless of
the directory pytest is invoked from, and guarantee the dry-run's throwaway
study directory never survives the session."""
import os
import shutil
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DRYRUN_STUDY_DIR = os.path.join(_REPO_ROOT, "studies", "copilot_dryrun")


@pytest.fixture(scope="session", autouse=True)
def _clean_dryrun_study_dir():
    """dry_run() writes to studies/copilot_dryrun/ and removes it in a finally;
    this is the backstop if a test process is interrupted mid-run."""
    shutil.rmtree(_DRYRUN_STUDY_DIR, ignore_errors=True)
    yield
    shutil.rmtree(_DRYRUN_STUDY_DIR, ignore_errors=True)
