"""gender-pay-gap.html: regression tests for issue #16.

Expected values come from the preset numbers and a hand-written Oaxaca-Blinder
decomposition, never from the page itself.
"""

import json
import math

from playwright.sync_api import Page, expect

TOOL = "gender-pay-gap.html"
STORAGE_KEY = "gpg-decomposition-v1"

# Preset B as the page defines it: (X̄ men, X̄ women, β men, β women).
WAGE_M, WAGE_F = 27.05, 22.81
PRESET_B = [
    (0.12, 0.48, -0.14, -0.06),
    (0.29, 0.19, 0.22, 0.16),
    (0.46, 0.31, 0.20, 0.20),
    (21.0, 17.5, 0.0080, 0.0072),
    (13.4, 13.5, 0.0650, 0.0640),
]
BETA_M = [row[2] for row in PRESET_B]
BETA_F = [row[3] for row in PRESET_B]


def lp(value: float) -> str:
    """Log points with one decimal and a decimal comma, as the page shows them."""
    return f"{value * 100:.1f}".replace(".", ",")


def shown_betas(page: Page, column: int) -> list[float]:
    """Read one β column (2 = men, 3 = women) from the factor cards."""
    cards = page.locator("#factorList .factor")
    return [
        float(cards.nth(i).locator(".inputs-grid input").nth(column).input_value())
        for i in range(cards.count())
    ]


def stored_betas_f(page: Page) -> list[float]:
    stored = json.loads(page.evaluate(f"localStorage.getItem('{STORAGE_KEY}')"))
    return [factor["bf"] for factor in stored["factors"]]


def test_equal_returns_toggle_leaves_the_entered_beta_f_alone(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    page.click("#presetB")
    toggle = page.locator("#equalReturns")

    toggle.check()
    # The βf fields show the βm the computation uses, while the entered βf
    # stays stored.
    assert shown_betas(page, 3) == BETA_M
    expect(page.locator("#factorList .inputs-grid input").nth(3)).to_be_disabled()
    assert stored_betas_f(page) == BETA_F

    # With βf = βm and the pooled reference β* = βm, nothing is unexplained per
    # factor: the explained part is Σ (X̄m − X̄f)·βm, the rest is unexplained.
    gap = math.log(WAGE_M / WAGE_F)
    explained = sum((xm - xf) * bm for xm, xf, bm, _ in PRESET_B)
    totals = page.locator("#totals .total-card")
    expect(totals.nth(1).locator(".label")).to_have_text("Erklärt")
    expect(totals.nth(1).locator(".sub")).to_have_text(
        f"{lp(explained)} LP · Ausstattung"
    )
    expect(totals.nth(2).locator(".label")).to_have_text("Unerklärt")
    expect(totals.nth(2).locator(".sub")).to_contain_text(f"{lp(gap - explained)} LP")

    page.reload(wait_until="networkidle")
    expect(toggle).to_be_checked()
    assert shown_betas(page, 3) == BETA_M

    toggle.uncheck()
    assert shown_betas(page, 3) == BETA_F
    assert stored_betas_f(page) == BETA_F
    expect(page.locator("#factorList .inputs-grid input").nth(3)).to_be_enabled()
    assert not tool.problems, "\n".join(tool.problems)
