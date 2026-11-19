# tools

Basic html tools inspired by the patterns presented at https://simonwillison.net/2025/Dec/10/html-tools/

https://fabiandistler.github.io/tools/

## Tests

`tests/` holds a Playwright smoke suite. It opens every root `*.html` at desktop and phone width and fails on console errors, page errors, failed requests, requests to other hosts, or a page that scrolls sideways on a phone. Multi-step tools also get a flow test that walks every path to the end. CI runs the suite on every pull request and push, and deploys to GitHub Pages only from `main` after it passes.

Run it locally with [uv](https://docs.astral.sh/uv/):

```sh
uv run playwright install chromium && uv run pytest
```

On a machine with Chrome already installed, such as a Claude Code cloud session, skip the download and use that browser:

```sh
uv run pytest --browser-channel chrome
```
