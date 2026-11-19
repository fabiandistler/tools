"""dfbetas-influence.html: the numbers match a brute-force refit, and the audit repros stay fixed.

The reference is numpy: refit the model n times, once without each row, and
compute DFBETAS from its definition. Issue #12 lists the repros.
"""

import csv
import io

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
