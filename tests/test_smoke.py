"""Every root tool loads cleanly at desktop and phone width.

The end-state check (``end_state.py``) runs after each load, so the phone row
also proves that the tool fits a phone screen when it opens.
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("viewport", ["desktop", "phone"])
def test_loads_without_errors(open_tool, tool_file, viewport):
    tool = open_tool(tool_file, viewport)
    assert not tool.problems, "\n".join(tool.problems)


def test_index_lists_every_tool(open_tool, tool_files):
    index = open_tool("index.html", "phone")
    links = index.page.locator("#tool-list a")
    tools_besides_index = sorted(set(tool_files) - {"index.html"})
    expect(links).to_have_count(len(tools_besides_index))
    hrefs = links.evaluate_all("links => links.map(link => link.getAttribute('href'))")
    assert sorted(hrefs) == tools_besides_index
