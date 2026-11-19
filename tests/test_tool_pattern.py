"""tool-pattern.html: regression tests for issue #16."""

import pytest
from playwright.sync_api import Page, expect

TOOL = "tool-pattern.html"
CORS_URL = "https://pypi.org/pypi/requests/json"


def open_panel(page: Page, panel: str) -> None:
    page.click(f'nav button[data-panel="{panel}"]')
    expect(page.locator(f"#panel-{panel}")).to_be_visible()


# --- Baustein 7: CORS checker -----------------------------------------------


@pytest.mark.parametrize(
    ("headers", "verdict"),
    [
        pytest.param({"Access-Control-Allow-Origin": "*"}, "✓ Erlaubt", id="allowed"),
        # Playwright adds a matching Allow-Origin to a fulfilled response that
        # has none, so the blocked case names another origin instead.
        pytest.param(
            {"Access-Control-Allow-Origin": "https://example.org"},
            "✗ Keine Antwort",
            id="permission-for-another-origin",
        ),
    ],
)
def test_cors_checker_reads_the_permission_from_the_fetch_outcome(
    open_tool, headers, verdict
):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    # Page routes win over the context route that blocks external hosts.
    page.route(
        CORS_URL,
        lambda route: route.fulfill(status=200, body="", headers=headers),
    )
    open_panel(page, "cors")
    page.fill("#cors-url", CORS_URL)
    page.click("button:has-text('Prüfen')")

    result = page.locator("#cors-result")
    expect(result).to_contain_text(verdict)
    # The page cannot read the header itself; the result says what it inferred
    # the answer from.
    expect(result).to_contain_text("Access-Control-Allow-Origin")
    # A blocked fetch makes the browser itself log errors about that URL.
    page_problems = [problem for problem in tool.problems if CORS_URL not in problem]
    assert not page_problems, "\n".join(page_problems)


# A same-origin fetch always succeeds, and an address without a scheme would
# resolve against this page, so neither may count as "✓ Erlaubt".
@pytest.mark.parametrize(
    ("address", "message"),
    [
        pytest.param("{site_url}/index.html", "dieselbe Adresse", id="same-origin"),
        pytest.param(
            "pypi.org/pypi/requests/json",
            "keine vollständige Webadresse",
            id="no-scheme",
        ),
    ],
)
def test_cors_checker_only_judges_a_foreign_web_address(
    open_tool, site_url, address, message
):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_panel(page, "cors")
    page.fill("#cors-url", address.format(site_url=site_url))
    page.click("button:has-text('Prüfen')")
    expect(page.locator("#cors-result")).to_contain_text(message)
    assert not tool.problems, "\n".join(tool.problems)
