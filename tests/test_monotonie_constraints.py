"""monotonie-constraints.html: regression tests for issue #16."""

from playwright.sync_api import Page, expect

TOOL = "monotonie-constraints.html"


def add_features(page: Page, *names: str) -> None:
    for name in names:
        page.fill("#featInput", name)
        page.click("#addBtn")


def page_widths(page: Page) -> dict[str, int]:
    return page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth,"
        " client: document.documentElement.clientWidth})"
    )


# --- Section 3: result table on a phone -------------------------------------


def test_result_table_scrolls_in_its_own_box_on_a_phone(open_tool):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    add_features(page, "Joblevel", "Berufserfahrung", "Standort")
    expect(page.locator("#summary tbody tr")).to_have_count(3)

    widths = page_widths(page)
    assert widths["scroll"] <= widths["client"], (
        f"page is {widths['scroll']} px wide on a {widths['client']} px screen"
    )
    # The last column stays reachable by scrolling the table's own box.
    last_header = page.locator("#summary th").last
    last_header.scroll_into_view_if_needed()
    expect(last_header).to_be_in_viewport()
    assert not tool.problems, "\n".join(tool.problems)
