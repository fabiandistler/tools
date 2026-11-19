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


# --- Baustein 2: clipboard --------------------------------------------------


def put_on_clipboard(page: Page, site_url: str, text: str) -> None:
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"], origin=site_url
    )
    page.evaluate("text => navigator.clipboard.writeText(text)", text)


def test_paste_into_the_transform_field_lands_in_the_field(open_tool, site_url):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_panel(page, "clipboard")
    put_on_clipboard(page, site_url, "Hallo Welt")

    page.focus("#transform-input")
    page.keyboard.press("ControlOrMeta+V")

    expect(page.locator("#transform-input")).to_have_value("Hallo Welt")
    expect(page.locator("#clip-content")).to_have_text("Hier erscheint der Inhalt …")
    assert not tool.problems, "\n".join(tool.problems)


def test_paste_outside_a_field_still_feeds_the_inspector(open_tool, site_url):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_panel(page, "clipboard")
    put_on_clipboard(page, site_url, "Hallo Welt")

    page.click("#panel-clipboard h2")
    page.keyboard.press("ControlOrMeta+V")

    expect(page.locator("#clip-content")).to_have_text("Hallo Welt")
    expect(page.locator("#transform-input")).to_have_value("")
    assert not tool.problems, "\n".join(tool.problems)


# --- Blocked browser storage -------------------------------------------------

# Safari with "Alle Cookies blockieren" (and Chrome with site data blocked)
# throws on every read of window.localStorage.
BLOCK_STORAGE = """
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  get() { throw new DOMException('The operation is insecure.', 'SecurityError'); },
});
"""
STORAGE_BLOCKED = "kein Speichern zu"


def test_blocked_storage_leaves_the_rest_of_the_page_working(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.add_init_script(BLOCK_STORAGE)
    page.reload(wait_until="networkidle")

    # Set up after the first storage read: drag and drop, the key display and
    # the LLM status.
    drop_prevented = page.evaluate(
        """() => {
            const event = new DragEvent('dragover', {bubbles: true, cancelable: true});
            document.getElementById('drop-zone').dispatchEvent(event);
            return event.defaultPrevented;
        }"""
    )
    assert drop_prevented, "the drop zone has no dragover listener"
    assert page.evaluate("document.getElementById('key-display-area').tabIndex") == 0

    open_panel(page, "llm")
    expect(page.locator("#llm-key-status")).to_contain_text(STORAGE_BLOCKED)

    open_panel(page, "localstorage")
    expect(page.locator("#ls-status")).to_contain_text(STORAGE_BLOCKED)
    expect(page.locator("#key-status")).to_contain_text(STORAGE_BLOCKED)

    page.fill("#ls-editor", "eine Notiz")
    expect(page.locator("#ls-wordcount")).to_have_text("2 Wörter")
    page.wait_for_timeout(1000)  # the draft is saved 800 ms after typing stops
    expect(page.locator("#ls-status")).to_contain_text(STORAGE_BLOCKED)

    page.once("dialog", lambda dialog: dialog.accept("beispiel-schluessel-1234"))
    page.click("button:has-text('Beispiel-Schlüssel setzen')")
    expect(page.locator("#key-status")).to_contain_text(STORAGE_BLOCKED)

    assert not tool.problems, "\n".join(tool.problems)


def test_draft_is_kept_across_a_reload_when_storage_works(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_panel(page, "localstorage")
    page.fill("#ls-editor", "eine Notiz")
    expect(page.locator("#ls-status")).to_contain_text("gespeichert ✓")

    page.reload(wait_until="networkidle")
    expect(page.locator("#ls-editor")).to_have_value("eine Notiz")
    expect(page.locator("#ls-status")).to_have_text("aus dem Browser-Speicher geholt")
    assert not tool.problems, "\n".join(tool.problems)
