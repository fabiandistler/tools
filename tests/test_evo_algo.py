"""evo-algo.html: a default run evolves within a minute.

The simulation takes one step per animation frame and draws every number from
``Math.random``. The tests replace ``Math.random`` with a seeded generator and
drive frames with Playwright's fake clock, so every run is the same.
"""

import pytest
from playwright.sync_api import Page, expect

TOOL = "evo-algo.html"

# mulberry32, a small seeded generator, in place of Math.random.
SEEDED_RANDOM = """
(() => {
  let seed = %d >>> 0;
  Math.random = () => {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();
"""

# Painting is not under test and takes most of each frame; without it a
# simulated minute runs in about two seconds. The simulation never reads pixels
# back, so it computes the same run either way.
NO_PAINTING = """
for (const method of ["fill", "fillRect", "stroke"]) {
  CanvasRenderingContext2D.prototype[method] = () => {};
}
"""

# Playwright's fake clock fires requestAnimationFrame every 16 ms; the tool's
# clock ("Epoche (Zeit)") counts 60 frames as one second.
FRAME_MS = 16
FRAMES_PER_SECOND = 60
START_POPULATION = 40


def reload_with_time_stopped(page: Page, *init_scripts: str) -> None:
    """Reload the tool after ``init_scripts``, with no frame running until a test asks."""
    for script in init_scripts:
        page.add_init_script(script)
    page.clock.install(time=0)
    page.clock.pause_at(1)
    page.reload()


@pytest.mark.parametrize("viewport", ["desktop", "phone"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_default_run_keeps_population_and_passes_generation_10(
    open_tool, viewport, seed
):
    tool = open_tool(TOOL, viewport)
    page = tool.page
    reload_with_time_stopped(page, SEEDED_RANDOM % seed, NO_PAINTING)

    page.clock.run_for(60 * FRAMES_PER_SECOND * FRAME_MS)

    assert not tool.problems, "\n".join(tool.problems)
    # Extinction restarts the run, which sets the clock back to 0.
    expect(page.locator("#stat-time")).to_have_text("60")
    population = int(page.locator("#stat-pop").inner_text())
    generation = int(page.locator("#stat-gen").inner_text())
    assert population >= START_POPULATION
    assert generation > 10
