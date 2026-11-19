"""``-k <tool name>`` selects the tool's own tests and its smoke rows, in either spelling."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def collected(*args: str) -> set[str]:
    listing = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout
    return {line for line in listing.splitlines() if "::" in line}


def test_either_spelling_of_a_tool_selects_its_module_and_smoke_rows():
    module = collected("tests/test_dfbetas_influence.py")
    smoke_rows = {
        test_id
        for test_id in collected("tests/test_smoke.py")
        if "[dfbetas-influence.html-" in test_id
    }
    assert module and smoke_rows

    for spelling in [
        "dfbetas-influence",
        "dfbetas_influence",
        "dfbetas-influence.html",
    ]:
        assert collected("-k", spelling) == module | smoke_rows, spelling
