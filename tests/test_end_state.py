"""The end-state check in end_state.py: it fails a test, and its message names the culprit."""

from pathlib import Path

import end_state
import pytest
from end_state import EndStateFailure, Failure
from playwright.sync_api import expect

MINCER = "mincer-gleichung.html"
# The fix for mincer's NaN axis (#16), and the line it replaced.
MINCER_FIX = "Number.isFinite(person.s) && !LEVELS.some(l => l.s === person.s)"
MINCER_BUG = "!LEVELS.some(l => l.s === person.s)"

PHONE_META = '<meta name="viewport" content="width=device-width, initial-scale=1">'


@pytest.mark.xfail(
    strict=True,
    raises=EndStateFailure,
    reason="proof: mincer's NaN axis (#16) fails a test that ends on it",
)
def test_a_test_ending_on_mincers_nan_axis_fails(open_tool):
    source = (Path(__file__).parent.parent / MINCER).read_text(encoding="utf-8")
    assert MINCER_FIX in source, f"the fix for #16 is gone from {MINCER}"
    tool = open_tool(MINCER, "desktop")
    page = tool.page
    page.route(
        f"**/{MINCER}",
        lambda route: route.fulfill(
            body=source.replace(MINCER_FIX, MINCER_BUG),
            content_type="text/html; charset=utf-8",
        ),
    )
    page.reload(wait_until="networkidle")
    page.click('#tabs button[data-panel="p-interaktiv"]')

    page.fill("#in-s", "")
    expect(page.locator("#person-msg")).to_have_text(
        "Bitte Bildungsjahre und Alter angeben."
    )
    assert not tool.problems, "\n".join(tool.problems)


@pytest.mark.end_state_exempt(
    "nan-text", reason="the test puts these words on screen to read the check"
)
def test_nan_text_names_each_visible_word_outside_code(open_tool):
    page = open_tool("index.html", "desktop").page
    page.set_content(
        """
        <main id="shown">
          <p class="result">Faktor: Infinity</p>
          <svg><text class="tick" y="20">NaN</text></svg>
          <canvas id="axis"></canvas>
          <pre>NaN</pre>
          <p><code>undefined</code></p>
          <textarea>Infinity</textarea>
          <input value="NaN">
          <p hidden>NaN</p>
          <p style="visibility: hidden">undefined</p>
          <p style="opacity: 0">NaN</p>
          <canvas id="hidden-axis" hidden></canvas>
          <p>Infinityband, NaNa, undefinedness</p>
        </main>
        """
    )
    page.evaluate(
        """() => {
          for (const id of ['axis', 'hidden-axis']) {
            document.getElementById(id).getContext('2d').fillText('undefined €', 0, 20);
          }
        }"""
    )

    failures = end_state.find_failures(page, "index.html", "desktop")

    assert failures == [
        Failure(
            "nan-text", "index.html", "desktop", "#shown p.result", "shows Infinity"
        ),
        Failure("nan-text", "index.html", "desktop", "#shown text.tick", "shows NaN"),
        Failure("nan-text", "index.html", "desktop", "canvas#axis", "draws undefined"),
    ]
    assert str(EndStateFailure(failures[:1])) == (
        "the page this test ends on fails the end-state check:\n"
        "- nan-text: index.html at desktop width: #shown p.result (shows Infinity)"
    )


def test_a_cleared_canvas_drops_its_old_text(open_tool):
    page = open_tool("index.html", "desktop").page
    page.set_content('<canvas id="chart"></canvas>')
    page.evaluate(
        """() => {
          const canvas = document.getElementById('chart');
          const context = canvas.getContext('2d');
          context.fillText('NaN', 0, 20);
          canvas.width = 200;
          context.fillText('12 €', 0, 20);
        }"""
    )

    assert end_state.find_failures(page, "index.html", "desktop") == []


@pytest.mark.end_state_exempt(
    "sideways-scroll", reason="the test widens the page to read the check"
)
def test_sideways_scroll_names_the_element_that_sticks_out(open_tool):
    page = open_tool("index.html", "phone").page
    page.set_content(
        f"""
        <head>{PHONE_META}</head>
        <body style="margin: 0">
          <main id="app">
            <div style="overflow-x: auto"><table style="width: 900px"><tr>
              <td>wide, but inside its own scroll box</td>
            </tr></table></div>
            <p class="row"><span class="cell" style="display: inline-block; width: 600px">
              too wide</span></p>
          </main>
        </body>
        """
    )

    assert end_state.find_failures(page, "index.html", "phone") == [
        Failure(
            "sideways-scroll",
            "index.html",
            "phone",
            "#app span.cell",
            "the page is 600 px wide on a 375 px screen",
        )
    ]


def test_sideways_scroll_is_a_phone_check(open_tool):
    page = open_tool("index.html", "desktop").page
    page.set_content('<div style="width: 2000px">wide</div>')

    assert end_state.find_failures(page, "index.html", "desktop") == []


@pytest.mark.parametrize(
    "mark",
    [
        pytest.mark.end_state_exempt("nan-text"),
        pytest.mark.end_state_exempt("nan-text", reason=" "),
        pytest.mark.end_state_exempt("overflow", reason="not a check"),
        pytest.mark.end_state_exempt(reason="names no check"),
    ],
    ids=["no-reason", "blank-reason", "unknown-check", "no-check"],
)
def test_an_exemption_needs_a_check_and_a_reason(mark):
    with pytest.raises(pytest.UsageError, match="end_state_exempt"):
        end_state.exemptions([mark.mark])


@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,
    reason="proof: an exemption whose check passes fails the test",
)
@pytest.mark.end_state_exempt("nan-text", reason="none: the index shows no NaN")
def test_an_unused_exemption_fails_the_test(open_tool):
    open_tool("index.html", "desktop")
