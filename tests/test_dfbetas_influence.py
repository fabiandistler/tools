"""dfbetas-influence.html: the numbers match a brute-force refit, and the audit repros stay fixed.

The reference is numpy: refit the model n times, once without each row, and
compute DFBETAS from its definition. Issue #12 lists the repros.
"""

import csv
import io
import re

import numpy as np
import pytest
from playwright.sync_api import Page, expect

TOOL = "dfbetas-influence.html"
# The audit matched the tool to a brute-force refit within 5e-7 on every demo.
DFBETAS_TOLERANCE = 5e-7

# Demo button, then the design the tool builds by default: the intercept, then
# one column per numeric predictor and one dummy per non-reference level, in
# file order. The id column is the row label, the last numeric column is y.
DEMOS = {
    "demo1": ["(Intercept)", "x"],
    "demo2": ["(Intercept)", "x"],
    "demo3": ["(Intercept)", "size", "age", "rooms"],
    "demoCat": ["(Intercept)", "region=south", "region=west", "spend"],
}


def read_data(page: Page, text: str) -> None:
    page.fill("#dataIn", text)
    page.click("#parseBtn")


def run(page: Page) -> None:
    page.click("#runBtn")
    expect(page.locator("#diagCard")).to_be_visible()


def fitted_dfbetas(page: Page) -> tuple[list[str], np.ndarray]:
    """Term names and DFBETAS at full precision, as the table and export get them.

    The CSV export rounds to 8 significant digits, which alone is up to 5e-7
    off once |DFBETAS| reaches 10, as it does in demos 2 and 3.
    """
    fit = page.evaluate(
        "() => ({names: S.fit.names, dfbetas: S.fit.dfbetas.map(r => Array.from(r))})"
    )
    return fit["names"], np.array(fit["dfbetas"])


def fitted_coefficients(page: Page) -> dict[str, float]:
    fit = page.evaluate("() => ({names: S.fit.names, b: Array.from(S.fit.b)})")
    return dict(zip(fit["names"], fit["b"], strict=True))


def ols(x: list[float], y: list[float]) -> dict[str, float]:
    X = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(X, np.array(y), rcond=None)[0]
    return {"(Intercept)": intercept, "x": slope}


def design_from_csv(text: str, terms: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Build X and y from comma-separated demo text, independently of the tool."""
    rows = list(csv.DictReader(io.StringIO(text)))
    y_name = list(rows[0])[-1]
    columns = []
    for term in terms:
        if term == "(Intercept)":
            columns.append([1.0] * len(rows))
        elif "=" in term:
            name, level = term.split("=")
            columns.append([float(row[name] == level) for row in rows])
        else:
            columns.append([float(row[term]) for row in rows])
    X = np.array(columns).T
    y = np.array([float(row[y_name]) for row in rows])
    return X, y


def brute_force_dfbetas(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """DFBETAS_j(i) = (b_j - b_j(i)) / (s_(i) * sqrt((X'X)^-1_jj)), by n refits."""
    n, p = X.shape
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    xtx_inv_diag = np.diag(np.linalg.inv(X.T @ X))
    dfbetas = np.empty((n, p))
    for i in range(n):
        keep = np.arange(n) != i
        b_without = np.linalg.lstsq(X[keep], y[keep], rcond=None)[0]
        resid = y[keep] - X[keep] @ b_without
        s_without = np.sqrt(resid @ resid / (n - 1 - p))
        dfbetas[i] = (b - b_without) / (s_without * np.sqrt(xtx_inv_diag))
    return dfbetas


@pytest.mark.parametrize(("demo", "terms"), DEMOS.items(), ids=DEMOS.keys())
def test_demo_dfbetas_match_brute_force_refit(open_tool, demo, terms):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.click(f"#{demo}")
    run(page)
    names, actual = fitted_dfbetas(page)
    assert not tool.problems, "\n".join(tool.problems)

    assert names == terms
    X, y = design_from_csv(page.input_value("#dataIn"), terms)
    expected = brute_force_dfbetas(X, y)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=DFBETAS_TOLERANCE)


# The audit repro: semicolon-separated, decimal points.
X_VALUES = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
Y_VALUES = [2.1, 3.9, 6.2, 8.1, 9.7, 12.4]


def as_text(sep: str, x_cells: list[str], y_cells: list[str]) -> str:
    return "\n".join([f"x{sep}y"] + [f"{a}{sep}{b}" for a, b in zip(x_cells, y_cells)])


def as_cells(values: list[float], decimal_mark: str) -> list[str]:
    return [f"{v:g}".replace(".", decimal_mark) for v in values]


@pytest.mark.parametrize(
    ("sep", "decimal_mark"),
    [(";", "."), (";", ","), (",", "."), ("\t", ","), ("\t", ".")],
    ids=["semicolon-point", "semicolon-comma", "comma-point", "tab-comma", "tab-point"],
)
def test_decimal_mark_comes_from_the_values_not_the_separator(
    open_tool, sep, decimal_mark
):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    x_cells = as_cells(X_VALUES, decimal_mark)
    y_cells = as_cells(Y_VALUES, decimal_mark)
    read_data(page, as_text(sep, x_cells, y_cells))
    mark_name = "decimal point" if decimal_mark == "." else "decimal comma"
    expect(page.locator("#parseMsg")).to_contain_text(mark_name)
    run(page)
    assert not tool.problems, "\n".join(tool.problems)

    expected = ols(X_VALUES, Y_VALUES)
    # The audit read -10.25 here, from 1.5 taken as 15.
    assert expected["(Intercept)"] == pytest.approx(-1.02, abs=0.005)
    assert fitted_coefficients(page) == pytest.approx(expected, abs=1e-9)


# Issue #11's repro, read once with each decimal mark and grouping style.
REVENUE = [1234.50, 2345.00, 3456.75, 4567.25, 5678.00, 6789.90]
COST = [10, 12, 15, 16, 19, 23]
REVENUE_FORMATS = {
    "german-grouped": (
        ";",
        ["1.234,50", "2.345,00", "3.456,75", "4.567,25", "5.678,00", "6.789,90"],
    ),
    "german-plain": (
        ";",
        ["1234,50", "2345,00", "3456,75", "4567,25", "5678,00", "6789,90"],
    ),
    "point-plain": (
        ",",
        ["1234.50", "2345.00", "3456.75", "4567.25", "5678.00", "6789.90"],
    ),
    "point-grouped": (
        ",",
        [
            '"1,234.50"',
            '"2,345.00"',
            '"3,456.75"',
            '"4,567.25"',
            '"5,678.00"',
            '"6,789.90"',
        ],
    ),
    "german-grouped-quoted": (
        ",",
        [
            '"1.234,50"',
            '"2.345,00"',
            '"3.456,75"',
            '"4.567,25"',
            '"5.678,00"',
            '"6.789,90"',
        ],
    ),
}


@pytest.mark.parametrize("cells", REVENUE_FORMATS.values(), ids=REVENUE_FORMATS.keys())
def test_thousands_grouping_and_decimal_mark_give_the_same_fit(open_tool, cells):
    sep, revenue_cells = cells
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, as_text(sep, revenue_cells, [str(c) for c in COST]))
    run(page)
    assert not tool.problems, "\n".join(tool.problems)
    assert fitted_coefficients(page) == pytest.approx(ols(REVENUE, COST), rel=1e-9)


@pytest.mark.parametrize("n_rows", [24, 7], ids=["24-rows", "7-rows"])
@pytest.mark.parametrize("bad_cell", ["10 kg", "1.2.3", "12%", "0x10", "1e999", "5."])
def test_cell_that_is_not_wholly_a_number_is_rejected_and_named(
    open_tool, bad_cell, n_rows
):
    x = [float(i) for i in range(1, n_rows + 1)]
    y = [2.0 + 0.5 * v + (0.3 if i % 2 else -0.3) for i, v in enumerate(x)]
    y_cells = [f"{v:g}" for v in y]
    bad_row = 6
    y_cells[bad_row - 1] = bad_cell
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, as_text(",", [f"{v:g}" for v in x], y_cells))
    # Pasted line numbers: the header is line 1.
    expect(page.locator("#parseMsg .msg.warn")).to_contain_text(
        f"y: line {bad_row + 1}"
    )
    run(page)
    assert not tool.problems, "\n".join(tool.problems)

    expect(page.locator("#modelMsg")).to_contain_text("1 row(s) dropped")
    kept = [i for i in range(len(x)) if i != bad_row - 1]
    expected = ols([x[i] for i in kept], [y[i] for i in kept])
    assert fitted_coefficients(page) == pytest.approx(expected, abs=1e-9)


def test_leading_zero_is_not_a_thousands_group(open_tool):
    # With a decimal comma, "0.125" is no number: a thousands group never
    # starts with 0, so reading it as 125 would be a silent misread.
    y_cells = as_cells(Y_VALUES, ",")
    y_cells[2] = "0.125"
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, as_text(";", as_cells(X_VALUES, ","), y_cells))
    expect(page.locator("#parseMsg")).to_contain_text("decimal comma")
    expect(page.locator("#parseMsg .msg.warn")).to_contain_text("y: line 4")
    assert not tool.problems, "\n".join(tool.problems)


# The only "b" row (row 3) has leverage 1: without it, the g=b dummy is all zero.
SINGLE_LEVEL_ROW = 3
SINGLE_LEVEL_DATA = (
    "g,x,y\na,1,2\na,2,4.1\nb,3,5.9\na,4,8.2\na,5,9.8\nc,6,12.1\na,7,14\nc,8,16.3"
)
SINGLE_LEVEL_TERMS = ["(Intercept)", "g=b", "g=c", "x"]


def test_row_with_leverage_one_shows_a_message_not_a_number(open_tool):
    X, y = design_from_csv(SINGLE_LEVEL_DATA, SINGLE_LEVEL_TERMS)
    others = np.arange(len(y)) != SINGLE_LEVEL_ROW - 1
    # The refit without that row is not identified, so DFBETAS has no value.
    assert np.linalg.matrix_rank(X[others]) < X.shape[1]

    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, SINGLE_LEVEL_DATA)
    page.check('#xList input[value="g"]')
    run(page)
    names, actual = fitted_dfbetas(page)
    assert names == SINGLE_LEVEL_TERMS
    assert np.isnan(actual[SINGLE_LEVEL_ROW - 1]).all()
    # Every other row still matches the brute-force refit.
    expected = brute_force_dfbetas(X, y)
    np.testing.assert_allclose(
        actual[others], expected[others], rtol=0, atol=DFBETAS_TOLERANCE
    )

    expect(page.locator("#diagSummary")).to_contain_text(
        f"Row {SINGLE_LEVEL_ROW} has leverage h = 1"
    )
    row = page.locator(f'#diagTable tbody tr[data-i="{SINGLE_LEVEL_ROW - 1}"]')
    for cell in row.locator("td.cell").all_inner_texts():
        assert not re.search(r"\d", cell), cell
    expect(row).to_contain_text("h = 1")

    row.click()
    detail = page.locator("#detail")
    expect(detail).to_contain_text("leverage h = 1")
    expect(detail).not_to_contain_text("would not meaningfully change the model")
    assert not tool.problems, "\n".join(tool.problems)


def test_new_run_resets_the_sort_and_shows_the_most_influential_rows(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.click("#demo3")
    run(page)
    page.select_option("#topN", "15")
    page.click('#diagTable th[data-key="c3"]')  # the rooms column
    expect(page.locator("#diagTable th.active")).to_have_attribute("data-key", "c3")
    page.uncheck('#xList input[value="age"]')
    page.uncheck('#xList input[value="rooms"]')
    run(page)
    assert not tool.problems, "\n".join(tool.problems)

    expect(page.locator("#diagTable th.active")).to_have_attribute("data-key", "maxabs")
    terms = ["(Intercept)", "size"]
    X, y = design_from_csv(page.input_value("#dataIn"), terms)
    worst_first = np.argsort(-np.abs(brute_force_dfbetas(X, y)).max(axis=1))
    expected_labels = [str(i + 1) for i in worst_first[:15]]
    assert "36" in expected_labels
    shown = page.locator("#diagTable tbody td.idx").all_inner_texts()
    assert shown == expected_labels


def test_text_only_data_retires_the_previous_model(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.click("#demo1")
    run(page)
    read_data(page, "a,b\nfoo,bar\nbaz,qux\nx,z")

    expect(page.locator("#parseMsg .msg.err")).to_contain_text("No numeric column")
    # The old model card would fit the new data with the old column names.
    expect(page.locator("#modelCard")).to_be_hidden()
    expect(page.locator("#runBtn")).to_be_hidden()
    expect(page.locator("#fitCard")).to_be_hidden()
    expect(page.locator("#diagCard")).to_be_hidden()
    assert not tool.problems, "\n".join(tool.problems)


def test_index_plot_is_readable_and_tappable_on_a_phone(open_tool):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    # Demo 2 has 24 rows and DFBETAS past 10, so a long tick label.
    page.click("#demo2")
    run(page)
    plot = page.locator("#indexPlot")
    plot.scroll_into_view_if_needed()

    label_heights = plot.locator("text").evaluate_all(
        "texts => texts.map(t => t.getBoundingClientRect().height)"
    )
    assert min(label_heights) >= 11, label_heights
    plot_box = plot.bounding_box()
    assert plot_box is not None
    label_lefts = plot.locator("text").evaluate_all(
        "texts => texts.map(t => t.getBoundingClientRect().left)"
    )
    assert min(label_lefts) >= plot_box["x"], "a tick label is cut off"
    captions = plot.locator("text").evaluate_all(
        "texts => texts.slice(-2).map(t => t.getBoundingClientRect())"
        ".map(b => [b.left, b.top, b.right, b.bottom])"
    )
    (l1, t1, r1, b1), (l2, t2, r2, b2) = captions
    assert r1 <= l2 or r2 <= l1 or b1 <= t2 or b2 <= t1, "bottom captions overlap"

    # A finger lands near a point, not on it: 3 px beside and 10 px below row 5.
    point = plot.locator("circle").nth(4).bounding_box()
    assert point is not None
    page.touchscreen.tap(
        point["x"] + point["width"] / 2 + 3, point["y"] + point["height"] / 2 + 10
    )
    expect(page.locator("#detail h2")).to_have_text("Why row 5?")

    page.set_viewport_size({"width": 700, "height": 812})
    expect(plot).to_have_attribute(
        "viewBox", re.compile(rf"^0 0 {plot.evaluate('svg => svg.clientWidth')} ")
    )
    assert not tool.problems, "\n".join(tool.problems)
