"""Every root tool loads cleanly at desktop and phone width and fits a phone screen."""

import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("viewport", ["desktop", "phone"])
def test_loads_without_errors(open_tool, tool_file, viewport):
    tool = open_tool(tool_file, viewport)
    assert not tool.problems, "\n".join(tool.problems)


def test_page_does_not_scroll_sideways_on_phone(open_tool, tool_file):
    tool = open_tool(tool_file, "phone")
    widths = tool.page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth,"
        " client: document.documentElement.clientWidth})"
    )
    assert widths["scroll"] <= widths["client"], (
        f"page is {widths['scroll']} px wide on a {widths['client']} px screen"
    )


def test_index_lists_every_tool(open_tool, tool_files):
    index = open_tool("index.html", "phone")
    links = index.page.locator("#tool-list a")
    tools_besides_index = sorted(set(tool_files) - {"index.html"})
    expect(links).to_have_count(len(tools_besides_index))
    hrefs = links.evaluate_all("links => links.map(link => link.getAttribute('href'))")
    assert sorted(hrefs) == tools_besides_index
