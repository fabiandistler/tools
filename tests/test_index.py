"""index.html: regression tests for issue #15 (the page when the GitHub API fails).

The page lists the tools through the GitHub contents API. When that call
fails, it must say why and link to the repository instead of ending in a
dead end.
"""

from collections.abc import Callable

import pytest
from playwright.sync_api import Route, expect

REPO_URL = "https://github.com/fabiandistler/tools"
CORS = {"Access-Control-Allow-Origin": "*"}


def answer_with(status: int) -> Callable[[Route], None]:
    def answer(route: Route) -> None:
        route.fulfill(status=status, json={"message": f"HTTP {status}"}, headers=CORS)

    return answer


def answer_rate_limited(status: int) -> Callable[[Route], None]:
    """Answer as GitHub does once the unauthenticated hourly limit is used up."""

    def answer(route: Route) -> None:
        route.fulfill(
            status=status,
            json={"message": "API rate limit exceeded"},
            headers={**CORS, "X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "0"},
        )

    return answer


def drop_connection(route: Route) -> None:
    route.abort("internetdisconnected")


@pytest.mark.parametrize(
    ("answer", "reason", "not_reason"),
    [
        pytest.param(answer_rate_limited(403), "Limit der GitHub-API", None, id="403"),
        pytest.param(answer_rate_limited(429), "Limit der GitHub-API", None, id="429"),
        pytest.param(answer_with(500), "Serverfehler (HTTP 500)", "Limit", id="500"),
        pytest.param(answer_with(503), "Serverfehler (HTTP 503)", "Limit", id="503"),
        pytest.param(answer_with(404), "nicht gefunden (HTTP 404)", "Limit", id="404"),
        pytest.param(drop_connection, "nicht erreichbar", "Limit", id="offline"),
    ],
)
def test_failed_listing_says_why_and_links_the_repository(
    open_tool, answer, reason, not_reason
):
    tool = open_tool("index.html", "phone")
    page = tool.page
    page.route("https://api.github.com/**", answer)
    page.reload(wait_until="networkidle")

    failure = page.locator("#load-failure")
    expect(failure).to_be_visible()
    expect(failure).to_contain_text(reason)
    if not_reason:
        expect(failure).not_to_contain_text(not_reason)
    expect(failure.get_by_role("link")).to_have_attribute("href", REPO_URL)
    expect(page.locator("#tool-list li")).to_have_count(0)
    # The browser itself logs the failed request as a console error; the
    # page's own code must not throw.
    page_errors = [p for p in tool.problems if p.startswith("page error")]
    assert not page_errors, "\n".join(page_errors)
