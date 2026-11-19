"""The end-state check: what every test that opens a tool asserts after its last step.

Some bugs only show after input: a table that widens the page once rows are
added, a chart axis that reads "NaN" once a field is cleared. A load-time
check misses them, so ``conftest.py`` runs these checks on the page a test
ends on:

- ``sideways-scroll``: at phone width the page does not scroll sideways.
- ``nan-text``: no visible text, including text drawn on a visible canvas,
  shows ``NaN``, ``Infinity`` or ``undefined`` as a whole word. Text inside
  ``pre``, ``code``, ``textarea`` and ``input`` is exempt: code samples and
  typed input may show these words.

A test whose end state fails a check legitimately carries
``@pytest.mark.end_state_exempt("<check>", reason="...")``. The exemption is
strict, like the suite's xfails: when the check it names finds nothing, the
test fails until the mark goes. A real bug takes
``@pytest.mark.xfail(strict=True, raises=EndStateFailure, reason="#<issue>")``.

Failure messages name the check, the tool and the element, never the page's
text: a tool may show record values.
"""

from collections.abc import Iterable
from typing import NamedTuple

import pytest
from playwright.sync_api import Page

CHECKS = ("sideways-scroll", "nan-text")

# Runs before every page script. A canvas keeps pixels, not text, so this
# remembers per canvas the text drawn since it was last cleared or resized:
# the labels of the frame on screen. A partial clear also starts a new frame,
# which can only hide a label, never invent one.
RECORD_CANVAS_TEXT = """
(() => {
  const drawn = new WeakMap();
  const restart = canvas => drawn.set(canvas, []);
  const context = CanvasRenderingContext2D.prototype;
  for (const name of ['fillText', 'strokeText']) {
    const draw = context[name];
    context[name] = function (text, ...args) {
      if (!drawn.has(this.canvas)) restart(this.canvas);
      drawn.get(this.canvas).push(String(text));
      return draw.call(this, text, ...args);
    };
  }
  const clearRect = context.clearRect;
  context.clearRect = function (...args) {
    restart(this.canvas);
    return clearRect.apply(this, args);
  };
  for (const size of ['width', 'height']) {
    const property = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, size);
    Object.defineProperty(HTMLCanvasElement.prototype, size, {
      ...property,
      set(value) { restart(this); property.set.call(this, value); },
    });
  }
  Object.defineProperty(window, '__endStateCanvasText', {
    value: canvas => drawn.get(canvas) || [],
  });
})();
"""

FIND_FAILURES = """
phone => {
  const failures = [];
  const label = element => {
    const own = element.localName + (element.id ? '#' + element.id : '')
      + [...element.classList].slice(0, 2).map(name => '.' + name).join('');
    const anchor = element.id ? null : element.parentElement?.closest('[id]');
    return anchor ? `#${anchor.id} ${own}` : own;
  };

  // Of a set of nested elements, those that hold none of the others.
  const innermost = elements => {
    const holders = new Set();
    for (const element of elements) {
      for (let box = element.parentElement; box; box = box.parentElement) holders.add(box);
    }
    return [...elements].filter(element => !holders.has(element));
  };

  const root = document.documentElement;
  const overflows = () => root.scrollWidth > root.clientWidth;
  if (phone && overflows()) {
    const detail = `the page is ${root.scrollWidth} px wide on a ${root.clientWidth} px screen`;
    const edge = root.clientWidth + 0.5;
    // A box that clips or scrolls its overflow holds its children in.
    const clipped = element => {
      for (let box = element.parentElement; box && box !== document.body; box = box.parentElement) {
        if (getComputedStyle(box).overflowX !== 'visible') return true;
      }
      return false;
    };
    const out = [...document.body.querySelectorAll('*')].filter(element =>
      element.getBoundingClientRect().right + scrollX > edge && !clipped(element));
    // Everything in a column that a wide preview stretches sticks out, so the
    // culprit is the smallest element whose removal ends the overflow.
    const removalFits = new Map();
    const fitsWithout = element => {
      if (!removalFits.has(element)) {
        const style = element.getAttribute('style');
        element.style.setProperty('display', 'none', 'important');
        removalFits.set(element, !overflows());
        if (style === null) element.removeAttribute('style');
        else element.setAttribute('style', style);
      }
      return removalFits.get(element);
    };
    const culprits = new Set();
    for (const element of innermost(out)) {
      let box = element;
      while (box !== document.body && !fitsWithout(box)) box = box.parentElement;
      culprits.add(box);
    }
    for (const element of culprits.size ? innermost(culprits) : [root]) {
      failures.push({check: 'sideways-scroll', element: label(element), detail});
    }
  }

  const word = /\\b(NaN|Infinity|undefined)\\b/;
  const visible = element => element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const match = word.exec(node.data);
    const element = node.parentElement;
    if (match && !element.closest('pre, code, textarea, input') && visible(element)) {
      failures.push({check: 'nan-text', element: label(element), detail: `shows ${match[1]}`});
    }
  }
  for (const canvas of document.querySelectorAll('canvas')) {
    if (!visible(canvas)) continue;
    for (const text of window.__endStateCanvasText(canvas)) {
      const match = word.exec(text);
      if (match) failures.push({check: 'nan-text', element: label(canvas), detail: `draws ${match[1]}`});
    }
  }
  return failures;
}
"""


class Failure(NamedTuple):
    check: str
    tool_file: str
    viewport: str
    element: str
    detail: str

    def __str__(self) -> str:
        return (
            f"{self.check}: {self.tool_file} at {self.viewport} width:"
            f" {self.element} ({self.detail})"
        )


class EndStateFailure(AssertionError):
    """A test ended on a page that fails an end-state check."""

    def __init__(self, failures: list[Failure]) -> None:
        lines = "\n".join(f"- {failure}" for failure in failures)
        super().__init__(
            f"the page this test ends on fails the end-state check:\n{lines}"
        )


def find_failures(page: Page, tool_file: str, viewport: str) -> list[Failure]:
    """Run every check on the page as it is now; duplicates are reported once."""
    found = page.evaluate(FIND_FAILURES, viewport == "phone")
    failures = [Failure(tool_file=tool_file, viewport=viewport, **row) for row in found]
    return list(dict.fromkeys(failures))


def exemptions(marks: Iterable[pytest.Mark]) -> dict[str, str]:
    """Map each check that ``end_state_exempt`` marks exempt to the mark's reason."""
    exempt = {}
    for mark in marks:
        check = mark.args[0] if len(mark.args) == 1 else None
        reason = str(mark.kwargs.get("reason", "")).strip()
        if check not in CHECKS or not reason:
            raise pytest.UsageError(
                "write end_state_exempt(<check>, reason=<why>) with one check out"
                f" of {', '.join(CHECKS)}"
            )
        exempt[check] = reason
    return exempt


def check(item: pytest.Item, failures: list[Failure]) -> None:
    """Fail the test on every failure its marks do not exempt, and on unused marks."""
    __tracebackhide__ = True
    exempt = exemptions(item.iter_markers("end_state_exempt"))
    unexempted = [failure for failure in failures if failure.check not in exempt]
    if unexempted:
        raise EndStateFailure(unexempted)
    unused = sorted(set(exempt) - {failure.check for failure in failures})
    if unused:
        pytest.fail(
            f"end_state_exempt({', '.join(unused)}) is unused: the page this test"
            " ends on passes that check, so remove the mark",
            pytrace=False,
        )
