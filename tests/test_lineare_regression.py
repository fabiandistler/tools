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


@pytest.mark.parametrize(
    ("pasted", "expected_columns", "decimal_name"),
    [
        # Decimal comma: "0.125" is no thousands group, so line 4 is skipped
        # instead of being read as 125.
        pytest.param(
            "x;y\n1,5;2,1\n2,5;3,9\n3,5;0.125\n4,5;8,1",
            [[1.5, 2.5, 4.5], [2.1, 3.9, 8.1]],
            "Komma",
            id="comma-rejects-0.125",
        ),
        # Decimal point: "0.125" can only be a decimal, so it votes for the
        # point and outweighs the one "4,5".
        pytest.param(
            "x;y\n1;0.125\n2;0.250\n3;0.375\n4;4,5",
            [[1.0, 2.0, 3.0], [0.125, 0.25, 0.375]],
            "Punkt",
            id="point-wins-with-0.125",
        ),
    ],
)
def test_a_thousands_group_never_starts_with_zero(
    open_tool, pasted, expected_columns, decimal_name
):
    tool = open_tool(TOOL, "desktop")
    read_data(tool.page, pasted)
    message = tool.page.locator("#d-msg")
    expect(message).to_contain_text(f"Dezimaltrennzeichen: {decimal_name}")
    expect(message).to_contain_text("Übersprungen")
    expect(message).to_contain_text("Zeile 4" if decimal_name == "Komma" else "Zeile 5")
    assert parsed_columns(tool.page) == expected_columns
    assert not tool.problems, "\n".join(tool.problems)


def test_too_few_numeric_rows_names_the_rejected_lines(open_tool):
    tool = open_tool(TOOL, "desktop")
    read_data(tool.page, "x;y\n1;10 kg\n2;20 kg\n3;30\n4;40")
    message = tool.page.locator("#d-msg")
    expect(message).to_contain_text("Zu wenige")
    expect(message).to_contain_text("Zeile 2, 3")
    expect(tool.page.locator("#d-config")).to_be_hidden()
    assert not tool.problems, "\n".join(tool.problems)


# --- Column names are text ---------------------------------------------------


def test_column_names_render_as_text(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    read_data(page, "x<b>;<i>y</i>\n1;2\n2;4,5\n3;5\n4;8")

    expect(page.locator("#d-y option")).to_have_text(["x<b>", "<i>y</i>"])
    expect(page.locator("#d-x label")).to_have_text(["x<b>"])
    page.click("#d-run")
    out = page.locator("#d-out")
    expect(out).to_contain_text("<i>y</i> ~ x<b>")
    expect(out).to_contain_text("x<b>: Steigt x<b> um eine Einheit")
    expect(out).to_contain_text("VIF x<b>")
    expect(out.locator("table").first.locator("tbody tr").nth(1)).to_contain_text(
        "x<b>"
    )
    expect(page.locator("#p-daten b, #p-daten i")).to_have_count(0)
    assert not tool.problems, "\n".join(tool.problems)


# --- Touch on the charts -----------------------------------------------------


def touch_swipe(page: Page, x: float, y_from: float, y_to: float) -> None:
    """Swipe one finger vertically, in viewport pixels, as a phone sends it."""
    cdp = page.context.new_cdp_session(page)
    steps = 12
    cdp.send(
        "Input.dispatchTouchEvent",
        {"type": "touchStart", "touchPoints": [{"x": x, "y": y_from}]},
    )
    for step in range(1, steps + 1):
        y = y_from + (y_to - y_from) * step / steps
        cdp.send(
            "Input.dispatchTouchEvent",
            {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]},
        )
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    cdp.detach()
    # Let the compositor apply the scroll before anyone reads scrollY.
    page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )


def place_near_viewport_top(page: Page, canvas_id: str) -> dict[str, float]:
    page.evaluate(
        "id => window.scrollTo(0, document.getElementById(id)"
        ".getBoundingClientRect().top + window.scrollY - 120)",
        canvas_id,
    )
    box = page.locator(f"#{canvas_id}").bounding_box()
    assert box is not None
    return box


def point_count(page: Page) -> int:
    return page.evaluate("() => ws.pts.length")


@pytest.mark.parametrize(
    ("panel_id", "canvas_id"),
    [("p-ols", "ols-canvas"), ("p-guete", "g-null"), ("p-inf", "i-hist")],
)
def test_swipe_on_a_chart_scrolls_the_page(open_tool, panel_id, canvas_id):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    open_tab(page, panel_id)
    box = place_near_viewport_top(page, canvas_id)
    scroll_before = page.evaluate("() => window.scrollY")
    points_before = point_count(page)

    # Start on the lower right of the chart, away from the OLS points.
    start_y = box["y"] + box["height"] - 45
    touch_swipe(page, box["x"] + box["width"] - 30, start_y, start_y - 200)

    scrolled = page.evaluate("() => window.scrollY") - scroll_before
    assert scrolled > 100, f"page scrolled {scrolled} px for a 200 px swipe"
    assert point_count(page) == points_before
    assert not tool.problems, "\n".join(tool.problems)


def plot_geometry(page: Page) -> dict[str, float]:
    return page.evaluate(
        "() => ({w: wsPlot.w, h: wsPlot.h, l: wsPlot.pad.l, r: wsPlot.pad.r,"
        " t: wsPlot.pad.t, b: wsPlot.pad.b, xmin: wsPlot.xmin, xmax: wsPlot.xmax,"
        " ymin: wsPlot.ymin, ymax: wsPlot.ymax})"
    )


def point_on_screen(page: Page, index: int) -> tuple[float, float]:
    box = page.locator("#ols-canvas").bounding_box()
    assert box is not None
    px, py = page.evaluate("i => [wsPlot.X(ws.pts[i].x), wsPlot.Y(ws.pts[i].y)]", index)
    return box["x"] + px, box["y"] + py


def test_tap_on_empty_plot_area_adds_a_point(open_tool):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    open_tab(page, "p-ols")
    box = place_near_viewport_top(page, "ols-canvas")
    plot = plot_geometry(page)
    page.touchscreen.tap(
        box["x"] + plot["w"] - plot["r"] - 20, box["y"] + plot["h"] - plot["b"] - 20
    )
    assert point_count(page) == 13
    assert not tool.problems, "\n".join(tool.problems)


def test_touch_drag_moves_a_point_without_scrolling(open_tool):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    open_tab(page, "p-ols")
    place_near_viewport_top(page, "ols-canvas")
    scroll_before = page.evaluate("() => window.scrollY")
    y_before = page.evaluate("() => ws.pts[5].y")

    x, y = point_on_screen(page, 5)
    touch_swipe(page, x, y, y + 60)

    assert page.evaluate("() => window.scrollY") == scroll_before
    assert page.evaluate("() => ws.pts[5].y") < y_before - 5
    assert point_count(page) == 12
    assert not tool.problems, "\n".join(tool.problems)


def test_mouse_click_adds_and_shift_click_removes(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_tab(page, "p-ols")
    box = page.locator("#ols-canvas").bounding_box()
    assert box is not None
    plot = plot_geometry(page)

    page.mouse.click(*point_on_screen(page, 3))
    assert point_count(page) == 12, "a click on a point must not add one"

    page.mouse.click(
        box["x"] + plot["w"] - plot["r"] - 20, box["y"] + plot["h"] - plot["b"] - 20
    )
    assert point_count(page) == 13

    page.keyboard.down("Shift")
    page.mouse.click(*point_on_screen(page, 0))
    page.keyboard.up("Shift")
    assert point_count(page) == 12
    assert not tool.problems, "\n".join(tool.problems)


# --- Dragging a point --------------------------------------------------------


def test_dragged_point_stays_under_the_pointer_near_the_top_edge(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_tab(page, "p-ols")
    box = page.locator("#ols-canvas").bounding_box()
    assert box is not None
    plot = plot_geometry(page)
    top_right = 11

    def y_under_pointer(py: float) -> float:
        # Inverse of the y axis of the plot as it was when the drag started.
        span = plot["h"] - plot["t"] - plot["b"]
        return plot["ymin"] + (plot["h"] - plot["b"] - py) / span * (
            plot["ymax"] - plot["ymin"]
        )

    x, y = point_on_screen(page, top_right)
    page.mouse.move(x, y)
    page.mouse.down()
    # Repro from issue #11: 15 px below the top edge, then a 1 px jitter.
    for move in range(10):
        py = 15 + move % 2
        page.mouse.move(x, box["y"] + py)
        dragged_y = page.evaluate("i => ws.pts[i].y", top_right)
        assert dragged_y == pytest.approx(y_under_pointer(py), abs=0.01), (
            f"move {move + 1}: the point left the pointer"
        )
    page.mouse.up()

    # After the drop the y axis fits the points and the line again, with the
    # page's 12 % margin, so the dragged point is no longer at the top edge.
    assert point_count(page) == 12
    points, b0, b1 = page.evaluate("() => [ws.pts, ws.b0, ws.b1]")
    heights = [p["y"] for p in points] + [b0 + b1 * p["x"] for p in points]
    low, high = min(heights), max(heights)
    assert page.evaluate("() => wsPlot.ymax") == pytest.approx(
        high + 0.12 * (high - low)
    )
    assert not tool.problems, "\n".join(tool.problems)
