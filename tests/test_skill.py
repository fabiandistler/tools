"""skill.html: regression tests for issue #15 (the Builder and the phone layout).

The generated frontmatter is read back with PyYAML, never with the page's own
code.
"""

import re

import pytest
import yaml
from playwright.sync_api import Page, expect

TOOL = "skill.html"
# The Builder ends the description with this line while no trigger phrases
# are entered.
EMPTY_TRIGGER_LINE = "Nutzen wenn: [Trigger-Phrasen eintragen]"


def open_section(page: Page, tab_label: str, section_id: str) -> None:
    page.locator("nav button", has_text=tab_label).click()
    expect(page.locator(f"#{section_id}")).to_be_visible()


def frontmatter(page: Page) -> dict:
    """Parse the YAML between the two ``---`` lines of the Builder preview."""
    template = page.locator("#template-output").text_content() or ""
    match = re.match(r"---\n(.*?\n)---\n", template, re.DOTALL)
    assert match, f"no frontmatter between two --- lines:\n{template}"
    return yaml.safe_load(match[1])


# --- Description: every line stays in the YAML block -----------------------


@pytest.mark.parametrize(
    ("what", "description_lines"),
    [
        pytest.param(
            "Zeile eins.\nZeile zwei: mit Doppelpunkt.",
            ["Zeile eins.", "Zeile zwei: mit Doppelpunkt."],
            id="issue-repro",
        ),
        pytest.param(
            "Absatz eins.\n\nAbsatz zwei.",
            ["Absatz eins.", "", "Absatz zwei."],
            id="empty-line",
        ),
        pytest.param(
            "Kein Markdown:\n# Titel\n- Punkt\n---\nkey: value",
            ["Kein Markdown:", "# Titel", "- Punkt", "---", "key: value"],
            id="yaml-syntax-at-line-start",
        ),
        pytest.param(
            "Liste:\n    eingerückt\n\tmit Tab",
            ["Liste:", "    eingerückt", "\tmit Tab"],
            id="indented-lines",
        ),
        # PyYAML reads U+2028 as a line break, so it must start an indented
        # line as well; it comes back as a plain newline.
        pytest.param(
            "Zeile eins. Zeile zwei: mit Doppelpunkt.",
            ["Zeile eins.", "Zeile zwei: mit Doppelpunkt."],
            id="unicode-line-separator",
        ),
    ],
)
def test_multi_line_description_is_valid_yaml(open_tool, what, description_lines):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    page.fill("#b-name", "pdf-summary")
    page.fill("#b-what", what)

    parsed = frontmatter(page)

    assert parsed == {
        "name": "pdf-summary",
        # A literal block scalar ("|") keeps one final newline.
        "description": "\n".join([*description_lines, EMPTY_TRIGGER_LINE]) + "\n",
    }
    assert not tool.problems, "\n".join(tool.problems)
