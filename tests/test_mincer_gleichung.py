"""mincer-gleichung.html: regression tests for issue #16."""

import math

from playwright.sync_api import Page, expect

TOOL = "mincer-gleichung.html"

# Records what the next chart draw writes and where it draws, starting at the
# clearRect() each draw begins with.
RECORD_CHART = """
window.chartDraw = { texts: [], points: [] };
const proto = CanvasRenderingContext2D.prototype;
const original = {
  clearRect: proto.clearRect, fillText: proto.fillText,
  moveTo: proto.moveTo, lineTo: proto.lineTo,
};
proto.clearRect = function (...args) {
  window.chartDraw = { texts: [], points: [] };
  return original.clearRect.apply(this, args);
};
proto.fillText = function (text, ...args) {
  window.chartDraw.texts.push(String(text));
  return original.fillText.call(this, text, ...args);
};
for (const name of ['moveTo', 'lineTo']) {
  proto[name] = function (x, y) {
    window.chartDraw.points.push([x, y]);
    return original[name].call(this, x, y);
  };
}
"""


def chart_draw(page: Page) -> dict:
    return page.evaluate("() => window.chartDraw")


def test_empty_education_field_keeps_the_chart_drawable(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.add_init_script(RECORD_CHART)
    page.reload(wait_until="networkidle")
    page.click('#tabs button[data-panel="p-interaktiv"]')

    # 13 years is one of the three drawn levels, so the person adds no curve
    # and the axis comes from the three level curves alone.
    expect(page.locator("#in-s")).to_have_value("13")
    on_a_level = chart_draw(page)

    page.fill("#in-s", "")
    expect(page.locator("#person-msg")).to_have_text(
        "Bitte Bildungsjahre und Alter angeben."
    )
    empty = chart_draw(page)

    assert not [text for text in empty["texts"] if "NaN" in text], empty["texts"]
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in empty["points"])
    # Same axis labels and the same curves as with S on a drawn level, minus
    # the person's dot, which is an arc, not a line.
    assert empty["texts"] == on_a_level["texts"]
    assert empty["points"] == on_a_level["points"]
    assert not tool.problems, "\n".join(tool.problems)
