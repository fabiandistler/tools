"""monotonie-constraints.html: regression tests for issue #16."""

import ast
import json

import pytest
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


# --- Section 4: generated code ----------------------------------------------

CODE_TABS = ["LightGBM", "XGBoost", "CatBoost", "scikit-learn", "AutoGluon", "H2O"]


def first_use_before_definition(source: str, name: str) -> int | None:
    """Line of the first top-level statement that reads `name` before one assigns it."""
    defined = False
    for statement in ast.parse(source).body:
        names = [node for node in ast.walk(statement) if isinstance(node, ast.Name)]
        reads = any(n.id == name and isinstance(n.ctx, ast.Load) for n in names)
        if reads and not defined:
            return statement.lineno
        defined = defined or any(
            n.id == name and isinstance(n.ctx, ast.Store) for n in names
        )
    return None


def copied_code(page: Page, site_url: str, tab: str) -> str:
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"], origin=site_url
    )
    page.click(f"#tabs button:has-text('{tab}')")
    page.click("#copyCode")
    expect(page.locator("#exportMsg")).to_have_text("Code kopiert.")
    return page.evaluate("() => navigator.clipboard.readText()")


@pytest.mark.parametrize("tab", CODE_TABS)
def test_copied_code_defines_feature_cols_before_using_it(open_tool, site_url, tab):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.click("#presetBtn")
    source = copied_code(page, site_url, tab)

    compile(source, f"{tab}.py", "exec")
    assert "feature_cols" in source
    line = first_use_before_definition(source, "feature_cols")
    assert line is None, f"{tab}: line {line} reads feature_cols before it is defined"
    assert not tool.problems, "\n".join(tool.problems)


# --- Section 5: validation checklist ----------------------------------------

TICKED = [0, 2, 6]


def checklist_items(page: Page) -> list[str]:
    return page.locator(".checklist label").evaluate_all(
        "labels => labels.map(label => label.textContent.trim())"
    )


def checklist_flags(page: Page) -> list[bool]:
    return page.locator(".checklist input[type=checkbox]").evaluate_all(
        "boxes => boxes.map(box => box.checked)"
    )


def test_checklist_is_kept_across_a_reload_and_exported(open_tool, site_url):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    add_features(page, "Joblevel")
    boxes = page.locator(".checklist input[type=checkbox]")
    for index in TICKED:
        boxes.nth(index).check()
    items = checklist_items(page)
    expected = [index in TICKED for index in range(len(items))]

    page.reload(wait_until="networkidle")
    assert checklist_flags(page) == expected

    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"], origin=site_url
    )
    page.click("#copyMd")
    expect(page.locator("#exportMsg")).to_have_text("Markdown kopiert.")
    markdown = page.evaluate("() => navigator.clipboard.readText()")
    for item, ticked in zip(items, expected, strict=True):
        assert f"- [{'x' if ticked else ' '}] {item}" in markdown.splitlines()

    with page.expect_download() as download_info:
        page.click("#dlJson")
    exported = json.loads(download_info.value.path().read_text(encoding="utf-8"))
    assert exported["validierung"] == [
        {"punkt": item, "erledigt": ticked}
        for item, ticked in zip(items, expected, strict=True)
    ]
    assert not tool.problems, "\n".join(tool.problems)
