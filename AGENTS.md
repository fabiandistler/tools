# Agents

A public gallery of single-file HTML tools, served at
https://fabiandistler.github.io/tools/. A merge publishes, so commit only
generic or synthetic data.

## Tools

- A tool is one root `<kebab-case-name>.html` file with its CSS and JS inline.
  `index.html` lists every root `.html` by itself, so a new tool needs no
  index edit.
- Build or fix a tool with the `html-tool-builder` skill; build an explainer
  with `html-artifacts`.
- Code and comments are English; the UI text stays German.
- New files stay under the prek hook's 5000-token limit (20000 bytes, about
  400 lines). A tool stays one file, so it meets the limit by cutting scope.
  The tools that predate the limit are exempt by name in
  `.pre-commit-config.yaml`, which gives the reason.

## Tests

- Every fix ships its repro as a test in `tests/`, red before the fix and green
  after it. Multi-step tools get a flow test that walks their paths to the end,
  like `tests/test_data_workflow.py`.
- `tests/test_smoke.py` already covers every root tool; `tests/conftest.py`
  holds the local server, the network block and the `open_tool` fixture.
- Every test that opens a tool ends with the end-state check (no sideways
  scroll on a phone, no visible `NaN`); `tests/end_state.py` says how to mark
  a known bug or a legitimate exception.
- Run the suite with `uv run pytest`. In a cloud session, use the installed
  Chrome with `uv run pytest --browser-channel chrome` and never
  `playwright install`. `README.md` has the one-time browser setup for a
  local machine.
- While fixing one tool, run its tests and smoke rows with `-k <tool-name>`
  (either spelling, e.g. `-k dfbetas-influence`) and leave the whole suite to
  CI. CI runs it in parallel (`-n auto`); local runs stay serial, because
  agents share the CPUs.

## Deploy gate

`.github/workflows/pages.yml` runs the suite on every pull request and push.
Only a push to `main` deploys, and only after the suite passes; the site holds
the root `*.html` files and nothing else. Open a pull request and leave the
merge to the owner: the merge deploys.
