"""lineare-regression.html: regression tests for issue #11.

Expected values come from Python's ``statistics`` module or from the plot
geometry, never from the page itself.
"""

import statistics

import pytest
from playwright.sync_api import Page, expect

TOOL = "lineare-regression.html"

# The repro from issue #11: German thousands and decimal separators.
GERMAN_SALES = (
    "umsatz;kosten\n1.234,50;10\n2.345,00;20\n3.100,25;31\n4.050,75;39\n5.200,00;52"
)
SALES = [1234.5, 2345.0, 3100.25, 4050.75, 5200.0]
COSTS = [10.0, 20.0, 31.0, 39.0, 52.0]


def open_tab(page: Page, panel_id: str) -> None:
    page.click(f'#tabs button[data-t="{panel_id}"]')
    expect(page.locator(f"#{panel_id}")).to_be_visible()


def read_data(page: Page, pasted: str) -> None:
    open_tab(page, "p-daten")
    page.fill("#d-input", pasted)
    page.click("#d-parse")


def parsed_columns(page: Page) -> list[list[float]]:
    return page.evaluate("() => dataset.cols")


def de(value: float, decimals: int) -> str:
    """Format a number as the page does: fixed decimals, decimal comma."""
    return f"{value:.{decimals}f}".replace(".", ",")


# --- Pasted numbers ---------------------------------------------------------


def test_german_numbers_are_read_whole(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, GERMAN_SALES)

    expect(page.locator("#d-msg")).to_contain_text("5 Zeilen, 2 Spalten eingelesen")
    expect(page.locator("#d-msg")).to_contain_text("Dezimaltrennzeichen: Komma")
    assert parsed_columns(page) == [SALES, COSTS]

    page.click("#d-run")
    reference = statistics.linear_regression(SALES, COSTS)
    slope_row = page.locator("#d-out table").first.locator(
        "tbody tr", has_text="umsatz"
    )
    expect(slope_row.locator("td").nth(1)).to_have_text(de(reference.slope, 3))
    intercept_row = page.locator("#d-out table").first.locator(
        "tbody tr", has_text="Achsenabschnitt"
    )
    expect(intercept_row.locator("td").nth(1)).to_have_text(de(reference.intercept, 3))
    assert not tool.problems, "\n".join(tool.problems)


@pytest.mark.parametrize(
    ("pasted", "expected_columns", "decimal_name"),
    [
        pytest.param(
            GERMAN_SALES.replace(";", "\t"), [SALES, COSTS], "Komma", id="tab-german"
        ),
        pytest.param(
            "x;y\n1234.50;10\n2345.00;20\n3100.25;31",
            [[1234.5, 2345.0, 3100.25], [10.0, 20.0, 31.0]],
            "Punkt",
            id="semicolon-point",
        ),
        pytest.param(
            "x,y\n1234.50,10\n2345.00,20\n3100.25,31",
            [[1234.5, 2345.0, 3100.25], [10.0, 20.0, 31.0]],
            "Punkt",
            id="comma-point",
        ),
        pytest.param(
            "x;y\n1,5;2\n2,5;3\n3,5;5",
            [[1.5, 2.5, 3.5], [2.0, 3.0, 5.0]],
            "Komma",
            id="semicolon-comma",
        ),
        pytest.param(
            "x;y\n1,234.50;10\n2,345.00;20\n3,100.25;31",
            [[1234.5, 2345.0, 3100.25], [10.0, 20.0, 31.0]],
            "Punkt",
            id="english-thousands",
        ),
        # "1.234" alone could be either; with no cell that decides it, the
        # point is the decimal separator, and the message says so.
        pytest.param(
            "x;y\n1.234;10\n2.345;20\n3.1;31",
            [[1.234, 2.345, 3.1], [10.0, 20.0, 31.0]],
            "Punkt",
            id="ambiguous-defaults-to-point",
        ),
    ],
)
def test_decimal_separator_comes_from_the_values(
    open_tool, pasted, expected_columns, decimal_name
):
    tool = open_tool(TOOL, "desktop")
    read_data(tool.page, pasted)
    expect(tool.page.locator("#d-msg")).to_contain_text(
        f"Dezimaltrennzeichen: {decimal_name}"
    )
    assert parsed_columns(tool.page) == expected_columns
    assert not tool.problems, "\n".join(tool.problems)


def test_cells_that_are_not_whole_numbers_are_rejected_and_named(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    # Lines 2, 4, 6 and 8 hold a unit, trailing letters, an empty cell and a date.
    read_data(
        page,
        "x;y\n1;10 kg\n2;20\n3;3abc\n4;41\n5;\n6;61\n2024-01-05;70",
    )
    message = page.locator("#d-msg")
    expect(message).to_contain_text("3 Zeilen, 2 Spalten eingelesen")
    expect(message).to_contain_text("Zeile 2, 4, 6, 8")
    assert parsed_columns(page) == [[2.0, 4.0, 6.0], [20.0, 41.0, 61.0]]
    assert not tool.problems, "\n".join(tool.problems)


def test_too_few_numeric_rows_names_the_rejected_lines(open_tool):
    tool = open_tool(TOOL, "desktop")
    read_data(tool.page, "x;y\n1;10 kg\n2;20 kg\n3;30\n4;40")
    message = tool.page.locator("#d-msg")
    expect(message).to_contain_text("Zu wenige")
    expect(message).to_contain_text("Zeile 2, 3")
    expect(tool.page.locator("#d-config")).to_be_hidden()
    assert not tool.problems, "\n".join(tool.problems)
