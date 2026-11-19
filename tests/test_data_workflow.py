"""data-workflow.html: every answer path ends on a filled result, and back and restart work.

Regression test for the end-of-workflow crash fixed in f07c5d8 and the
Cloudflare email-obfuscation leftovers removed in 08ecde7.
"""

import itertools
import re

import pytest
from playwright.sync_api import Page, expect

FORMATS = ["json", "xml", "csv", "yaml"]
DATABASES = ["sql", "document", "keyvalue", "graph", "vector"]
PATTERNS = ["direct", "repository", "orm"]
ANSWER_CARDS = {"step1": FORMATS, "step2": DATABASES, "step3": PATTERNS}
END_PATHS = list(itertools.product(FORMATS, DATABASES, PATTERNS))
RESULT_FIELDS = ["#resultFormat", "#resultDb", "#resultPattern", "#resultStack"]


@pytest.fixture
def workflow(open_tool):
    tool = open_tool("data-workflow.html", "phone")
    # Each step fades in for 0.3 s, which makes every click wait for it. The
    # animation is not under test.
    tool.page.add_style_tag(
        content="*, *::before, *::after"
        " { animation: none !important; transition: none !important; }"
    )
    return tool


def choose(page: Page, step_id: str, value: str, next_button_id: str) -> None:
    page.click(f'#{step_id} .option-card[data-value="{value}"]')
    page.click(f"#{next_button_id}")


def answer(page: Page, data_format: str, database: str, pattern: str) -> None:
    choose(page, "step1", data_format, "next1")
    choose(page, "step2", database, "next2")
    choose(page, "step3", pattern, "finish")


def assert_result_shown(workflow) -> None:
    # Errors first: a crash leaves the result hidden, and the error says why.
    assert not workflow.problems, "\n".join(workflow.problems)
    page = workflow.page
    expect(page.locator(".step.active")).to_have_count(1)
    expect(page.locator("#result")).to_be_visible()
    for field in RESULT_FIELDS:
        expect(page.locator(field)).not_to_be_empty()


def test_every_answer_has_an_end_path(workflow):
    # Guards the claim that END_PATHS covers the tool: a new answer card fails
    # here until it is added above.
    for step_id, values in ANSWER_CARDS.items():
        cards = workflow.page.locator(f"#{step_id} .option-card")
        card_values = cards.evaluate_all(
            "cards => cards.map(card => card.dataset.value)"
        )
        assert card_values == values, step_id


@pytest.mark.parametrize(
    ("data_format", "database", "pattern"),
    END_PATHS,
    ids=["-".join(path) for path in END_PATHS],
)
def test_end_path_shows_result(workflow, data_format, database, pattern):
    answer(workflow.page, data_format, database, pattern)
    assert_result_shown(workflow)


def test_back_then_changed_answer_reaches_result(workflow):
    page = workflow.page
    choose(page, "step1", "json", "next1")
    choose(page, "step2", "sql", "next2")
    page.click("#back3")
    page.click("#back2")
    answer(page, "csv", "sql", "repository")
    assert_result_shown(workflow)
    expect(page.locator("#resultFormat")).to_contain_text("CSV")


def test_restart_runs_a_second_workflow(workflow):
    page = workflow.page
    answer(page, "json", "document", "orm")
    assert_result_shown(workflow)
    page.click("#restart")
    answer(page, "yaml", "graph", "direct")
    assert_result_shown(workflow)
    expect(page.locator("#resultFormat")).to_contain_text("YAML")


def test_code_examples_show_email_addresses(workflow):
    # A copy saved from a Cloudflare-served page shows "[email protected]"
    # (with a no-break space) instead of each address.
    expect(workflow.page.locator("body")).not_to_contain_text(
        re.compile(r"\[email.protected\]")
    )
