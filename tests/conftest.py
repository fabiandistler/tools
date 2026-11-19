"""Serve the repository root over HTTP and open tools in a hermetic browser.

Every root ``*.html`` file is a tool, so a new tool is tested without an edit
here. Tests reach the tools through ``http://127.0.0.1``, not ``file://``, so
origin, ``localStorage`` and relative URLs behave as on GitHub Pages. Every
test that opens a tool ends with the checks in ``end_state.py``.
"""

import functools
import http.server
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import end_state
import pytest
from playwright.sync_api import ConsoleMessage, Error, Page, Request, Response, Route

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_FILES = sorted(path.name for path in REPO_ROOT.glob("*.html"))

# index.html lists the tools through the GitHub contents API. The tests answer
# that call themselves, so CI never depends on api.github.com or its
# unauthenticated rate limit.
GITHUB_CONTENTS_URL = "https://api.github.com/repos/fabiandistler/tools/contents/"

VIEWPORTS: dict[str, dict[str, Any]] = {
    "desktop": {"viewport": {"width": 1280, "height": 800}},
    # A narrow phone: the owner uses the tools on a phone.
    "phone": {
        "viewport": {"width": 375, "height": 812},
        "is_mobile": True,
        "has_touch": True,
    },
}


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "tool_file" in metafunc.fixturenames:
        metafunc.parametrize("tool_file", TOOL_FILES)


def _module_spelling(tool_file: str) -> str:
    """``dfbetas-influence.html`` is tested in ``test_dfbetas_influence.py``."""
    return Path(tool_file).stem.replace("-", "_")


TOOL_BY_MODULE = {f"test_{_module_spelling(name)}.py": name for name in TOOL_FILES}


def pytest_itemcollected(item: pytest.Item) -> None:
    """Let ``-k`` select a tool's tests by either spelling of its name.

    Smoke ids carry the file name and module names the underscored stem, so a
    bare ``-k dfbetas-influence`` used to pick the smoke rows alone. A test that
    takes the tool as ``tool_file`` or sits in its module gets both spellings.
    """
    callspec = getattr(item, "callspec", None)
    tool_file = callspec.params.get("tool_file") if callspec else None
    tool_file = tool_file or TOOL_BY_MODULE.get(item.path.name)
    if tool_file:
        item.extra_keyword_matches.update({tool_file, _module_spelling(tool_file)})


@pytest.fixture(scope="session")
def tool_files() -> list[str]:
    return TOOL_FILES


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        """Keep the per-request access log out of the test output."""


@pytest.fixture(scope="session")
def site_url() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=REPO_ROOT)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
        server.shutdown()


@dataclass
class OpenedTool:
    tool_file: str
    viewport: str
    page: Page
    # Console errors, page errors, failed same-origin requests and external
    # requests, in the order they happened. A clean tool leaves it empty.
    problems: list[str]


OPENED_TOOLS = pytest.StashKey[list[OpenedTool]]()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    """After a test passes its own asserts, check the pages it ends on.

    The check runs in the call phase, not in a fixture teardown, so a strict
    xfail sees its failure. ``tryfirst`` wraps pytest-playwright's own hook,
    which keeps its frames out of the failure report.
    """
    __tracebackhide__ = True
    outcome = yield
    failures = [
        failure
        for tool in item.stash.get(OPENED_TOOLS, [])
        for failure in end_state.find_failures(tool.page, tool.tool_file, tool.viewport)
    ]
    end_state.check(item, failures)
    return outcome


def _answer_external_request(route: Route, problems: list[str]) -> None:
    url = route.request.url
    if url == GITHUB_CONTENTS_URL:
        listing = [{"name": name, "type": "file"} for name in TOOL_FILES]
        route.fulfill(json=listing, headers={"Access-Control-Allow-Origin": "*"})
        return
    problems.append(f"external request (a tool must work offline): {url}")
    route.abort()


@pytest.fixture
def open_tool(
    new_context: Callable[..., Any], site_url: str, request: pytest.FixtureRequest
) -> Callable[[str, str], OpenedTool]:
    """Open a root tool at a named viewport and record everything that goes wrong."""

    def open_(tool_file: str, viewport: str) -> OpenedTool:
        context = new_context(**VIEWPORTS[viewport])
        context.add_init_script(end_state.RECORD_CANVAS_TEXT)
        problems: list[str] = []
        context.route(
            lambda url: not url.startswith(f"{site_url}/"),
            functools.partial(_answer_external_request, problems=problems),
        )
        page = context.new_page()

        def on_console(message: ConsoleMessage) -> None:
            if message.type == "error":
                problems.append(
                    f"console error: {message.text} @ {message.location['url']}"
                )

        def on_page_error(error: Error) -> None:
            problems.append(f"page error: {error.message}")

        def on_request_failed(request: Request) -> None:
            if request.url.startswith(f"{site_url}/"):
                problems.append(f"request failed: {request.url} ({request.failure})")

        def on_response(response: Response) -> None:
            if response.url.startswith(f"{site_url}/") and response.status >= 400:
                problems.append(f"HTTP {response.status}: {response.url}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)
        page.goto(f"{site_url}/{tool_file}", wait_until="networkidle")
        tool = OpenedTool(tool_file, viewport, page, problems)
        request.node.stash.setdefault(OPENED_TOOLS, []).append(tool)
        return tool

    return open_
