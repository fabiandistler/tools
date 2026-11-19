"""skill.html: regression tests for issues #15 and #22 (the Builder and the phone layout).

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


# --- Name and description: the limits the page teaches ----------------------

# The spec as the page states it on the Anatomie tab and in the checklist:
# name 1-64 characters of a-z, 0-9 and "-", no leading or trailing "-", no
# "--"; description 1-1024 characters.
NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024


def expect_rejected(page: Page, error_id: str, message: str) -> None:
    expect(page.locator(f"#{error_id}")).to_be_visible()
    expect(page.locator(f"#{error_id}")).to_contain_text(message)
    expect(page.locator("#b-copy")).to_be_disabled()


def expect_accepted(page: Page) -> None:
    expect(page.locator("#b-name-error")).to_be_hidden()
    expect(page.locator("#b-what-error")).to_be_hidden()
    expect(page.locator("#b-copy")).to_be_enabled()


@pytest.mark.parametrize(
    ("typed", "shown", "message"),
    [
        pytest.param("my-", "my-", "kein Bindestrich am Anfang oder Ende", id="end"),
        pytest.param("-my", "-my", "kein Bindestrich am Anfang oder Ende", id="start"),
        pytest.param("a--b", "a--b", "keine zwei Bindestriche", id="double"),
        pytest.param(
            "Mein Skill! Ä", "mein-skill!-ä", "nur Kleinbuchstaben a–z", id="chars"
        ),
        pytest.param(
            "a" * (NAME_MAX_LENGTH + 16),
            "a" * (NAME_MAX_LENGTH + 16),
            f"höchstens {NAME_MAX_LENGTH} Zeichen, jetzt {NAME_MAX_LENGTH + 16}",
            id="too-long",
        ),
    ],
)
def test_name_against_spec_is_rejected(open_tool, typed, shown, message):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    page.fill("#b-name", typed)

    expect_rejected(page, "b-name-error", message)
    # The preview follows the input instead of freezing on the last good name.
    assert frontmatter(page)["name"] == shown
    assert not tool.problems, "\n".join(tool.problems)


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        pytest.param("pdf-summary", "pdf-summary", id="plain"),
        pytest.param("PDF Summary", "pdf-summary", id="normalised"),
        pytest.param("v2-report-2026", "v2-report-2026", id="digits"),
        pytest.param("a" * NAME_MAX_LENGTH, "a" * NAME_MAX_LENGTH, id="at-limit"),
    ],
)
def test_name_within_spec_is_accepted(open_tool, typed, shown):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    page.fill("#b-name", typed)

    expect_accepted(page)
    assert frontmatter(page)["name"] == shown
    assert not tool.problems, "\n".join(tool.problems)


def test_typing_a_name_passes_through_a_trailing_hyphen(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    name_field = page.locator("#b-name")

    name_field.press_sequentially("my-")
    expect_rejected(page, "b-name-error", "kein Bindestrich am Anfang oder Ende")
    name_field.press_sequentially("skill")
    expect_accepted(page)
    assert frontmatter(page)["name"] == "my-skill"
    expect(page.locator("#template-output")).to_contain_text("# My Skill")
    assert not tool.problems, "\n".join(tool.problems)


@pytest.mark.parametrize(
    "over_limit", [0, 1, 476], ids=["at-limit", "one-over", "1500"]
)
def test_description_limit_counts_characters(open_tool, over_limit):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    # The description is "Was macht der Skill?", a newline, the trigger line
    # and the final newline the block keeps. One emoji makes the text one
    # character shorter than its JavaScript string length.
    expected_length = DESCRIPTION_MAX_LENGTH + over_limit
    filler_length = expected_length - len(EMPTY_TRIGGER_LINE) - 2
    page.fill("#b-what", "x" * (filler_length - 1) + "😀")

    assert len(frontmatter(page)["description"]) == expected_length
    if over_limit:
        expect_rejected(
            page,
            "b-what-error",
            f"{expected_length} von höchstens {DESCRIPTION_MAX_LENGTH} Zeichen",
        )
    else:
        expect_accepted(page)
    assert not tool.problems, "\n".join(tool.problems)


def test_reset_clears_a_rejected_name(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_section(page, "Builder", "builder")
    page.fill("#b-name", "a--b")
    expect_rejected(page, "b-name-error", "keine zwei Bindestriche")

    page.locator("#builder button", has_text="Reset").click()
    expect_accepted(page)
    assert not tool.problems, "\n".join(tool.problems)


# --- Builder on a phone -------------------------------------------------------


def test_builder_with_a_one_sentence_description_fits_a_phone(open_tool):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    open_section(page, "Builder", "builder")
    page.fill("#b-name", "pdf-summary")
    page.fill(
        "#b-what",
        "Fasst lange PDF-Berichte in fünf Stichpunkten zusammen und nennt die Seiten.",
    )

    expect(page.locator("#template-output")).to_contain_text("nennt die Seiten.")
    assert not tool.problems, "\n".join(tool.problems)
    # The end-state check asserts that the page does not scroll sideways.


# --- Komplexitätsstufen: annotated examples on a phone ----------------------


def open_level(page: Page, level: str) -> None:
    open_section(page, "Komplexitätsstufen", "levels")
    page.locator(".ctab", has_text=level.capitalize()).click()
    expect(page.locator(f"#level-{level}")).to_be_visible()


@pytest.mark.parametrize("level", ["simple", "medium", "complex"])
def test_level_example_code_gets_the_full_width_on_phone(open_tool, level):
    tool = open_tool(TOOL, "phone")
    page = tool.page
    open_level(page, level)
    example = page.locator(f"#level-{level} .annotation-box")
    code = example.locator("pre").bounding_box()
    notes = example.locator(".annotations").bounding_box()
    assert code and notes

    # The notes go below the code instead of squeezing it to a narrow strip.
    assert code["width"] == pytest.approx(notes["width"], abs=1)
    assert notes["y"] >= code["y"] + code["height"] - 1
    # And every note is shown in full, not cut off inside a scroll box.
    notes_overflow = example.locator(".annotations").evaluate(
        "notes => notes.scrollHeight - notes.clientHeight"
    )
    assert notes_overflow <= 0
    assert not tool.problems, "\n".join(tool.problems)


def test_level_example_keeps_notes_beside_code_on_desktop(open_tool):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_level(page, "simple")
    example = page.locator("#level-simple .annotation-box")
    code = example.locator("pre").bounding_box()
    notes = example.locator(".annotations").bounding_box()
    assert code and notes
    assert notes["x"] >= code["x"] + code["width"] - 1
