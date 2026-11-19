"""einsingen.html: regression tests for issue #14.

The pitch tests synthesize their own tones and feed them to the page's
``detectPitch`` exactly as the measuring loop does: one analyser window of
``pickFftSize(sampleRate)`` samples and the gate at the default sensitivity.
The expected note is the one the tone was built from, never a value the page
computes.

The microphone tests replace ``getUserMedia`` with a stream that carries a
steady A3 and log every ``AudioContext`` the page creates, closes and connects
the microphone to.
"""

import math

import pytest
from playwright.sync_api import Page, expect

TOOL = "einsingen.html"

# Installed before the page's own script runs.
FAKE_MICROPHONE = """
(() => {
  const NativeContext = window.AudioContext;
  const log = (window.audioLog = []);
  let count = 0;
  window.AudioContext = class extends NativeContext {
    constructor(...args) {
      super(...args);
      this.logId = ++count;
      log.push('new context ' + this.logId);
    }
    close() {
      log.push('close context ' + this.logId);
      return super.close();
    }
    // Set by a test to play a context that the system refuses to start: it
    // stays suspended and so never fires statechange.
    get state() {
      return window.contextNeverRuns ? 'suspended' : super.state;
    }
    set onstatechange(handler) {
      if (!window.contextNeverRuns) super.onstatechange = handler;
    }
    createMediaStreamSource(stream) {
      log.push('microphone on context ' + this.logId);
      return super.createMediaStreamSource(stream);
    }
  };
  navigator.mediaDevices.getUserMedia = async () => {
    log.push('getUserMedia');
    const singer = new NativeContext();
    const tone = singer.createOscillator();
    tone.frequency.value = 220;
    const stream = singer.createMediaStreamDestination();
    tone.connect(stream);
    tone.start();
    return stream.stream;
  };
})();
"""

SAMPLE_RATES = [44100, 48000]
# C2 (65.4 Hz) to D6 (1174.7 Hz): every semitone between the detector's
# F_MIN = 65 Hz and F_MAX = 1200 Hz. Exercises reach C6, the range tab higher.
MIDI_NOTES = range(36, 87)
NAMES = ["C", "Cis", "D", "Dis", "E", "F", "Fis", "G", "Gis", "A", "Ais", "H"]
PEAK_LEVEL = 0.1  # a phone microphone with its gain control switched off


def note_name(midi: int) -> str:
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_freq(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def sawtooth_amplitude(harmonic: int, freq: float) -> float:
    return 1 / harmonic


def vowel_a_amplitude(harmonic: int, freq: float) -> float:
    """A sawtooth source with formant bumps at 700 and 1100 Hz, as in "a"."""
    hz = harmonic * freq
    return (
        1 / harmonic
        + 1.5 * math.exp(-(((hz - 700) / 120) ** 2))
        + 1.0 * math.exp(-(((hz - 1100) / 150) ** 2))
    )


def vowel_u_amplitude(harmonic: int, freq: float) -> float:
    """A weak fundamental with formants at 300 and 800 Hz, as in "u"."""
    hz = harmonic * freq
    source = 0.3 if harmonic == 1 else 1 / harmonic
    return (
        source
        + 1.2 * math.exp(-(((hz - 300) / 80) ** 2))
        + 0.6 * math.exp(-(((hz - 800) / 120) ** 2))
    )


def vowel_i_amplitude(harmonic: int, freq: float) -> float:
    """A sawtooth source with a low formant and two high ones, as in "i"."""
    hz = harmonic * freq
    return (
        1 / harmonic
        + 0.8 * math.exp(-(((hz - 300) / 80) ** 2))
        + 1.2 * math.exp(-(((hz - 2300) / 200) ** 2))
        + 0.8 * math.exp(-(((hz - 3000) / 250) ** 2))
    )


WAVEFORMS = {
    "sawtooth": sawtooth_amplitude,
    "vowel-a": vowel_a_amplitude,
    "vowel-u": vowel_u_amplitude,
    "vowel-i": vowel_i_amplitude,
}


def harmonic_tone(amplitude, freq: float, sample_rate: int, length: int) -> list[float]:
    """Sum the harmonics below Nyquist (at most 30) and scale to PEAK_LEVEL."""
    samples = [0.0] * length
    harmonics = min(30, int(sample_rate / 2 // freq))
    for harmonic in range(1, harmonics + 1):
        gain = amplitude(harmonic, freq)
        step = 2 * math.pi * harmonic * freq / sample_rate
        phase = 0.9 * harmonic
        samples = [s + gain * math.sin(step * i + phase) for i, s in enumerate(samples)]
    peak = max(abs(s) for s in samples)
    return [round(s / peak * PEAK_LEVEL, 7) for s in samples]


def detect_all(page, sample_rate: int, tones: list[list[float]]) -> list[dict | None]:
    return page.evaluate(
        """([sampleRate, tones]) => tones.map(tone =>
            detectPitch(Float32Array.from(tone), sampleRate, gateLevel()))""",
        [sample_rate, tones],
    )


@pytest.mark.parametrize("sample_rate", SAMPLE_RATES)
@pytest.mark.parametrize("waveform", WAVEFORMS)
def test_harmonic_tones_read_in_the_right_octave(open_tool, waveform, sample_rate):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    window = page.evaluate("sr => pickFftSize(sr)", sample_rate)
    tones = [
        harmonic_tone(WAVEFORMS[waveform], midi_to_freq(m), sample_rate, window)
        for m in MIDI_NOTES
    ]
    detected = detect_all(page, sample_rate, tones)

    wrong = []
    for midi, result in zip(MIDI_NOTES, detected, strict=True):
        if result is None:
            wrong.append(f"{note_name(midi)}: nothing")
            continue
        cents = 1200 * math.log2(result["freq"] / midi_to_freq(midi))
        if abs(cents) > 10:
            wrong.append(
                f"{note_name(midi)}: {result['freq']:.1f} Hz ({cents:+.0f} ct)"
            )
    assert not wrong, f"{len(wrong)} of {len(MIDI_NOTES)} notes wrong: " + "; ".join(
        wrong
    )
    assert not tool.problems, "\n".join(tool.problems)


# --- Microphone and audio context ------------------------------------------


def open_with_fake_microphone(open_tool):
    tool = open_tool(TOOL, "desktop")
    tool.page.context.add_init_script(FAKE_MICROPHONE)
    tool.page.reload(wait_until="networkidle")
    return tool


def open_tab(page: Page, panel_id: str) -> None:
    page.click(f'#tabs button[data-t="{panel_id}"]')
    expect(page.locator(f"#{panel_id}")).to_be_visible()


def tap_a3_key(page: Page) -> None:
    page.click('#kbTuner .key[data-m="57"]')


def start_exercise(page: Page) -> None:
    open_tab(page, "p-uebung")
    page.click("#exStart")


def switch_microphone_on(page: Page) -> None:
    page.click("#micBtn")
    expect(page.locator("#micState")).to_have_text("Mikrofon läuft.")


@pytest.mark.parametrize("first_sound", [tap_a3_key, start_exercise])
def test_microphone_gets_a_context_started_after_its_stream(open_tool, first_sound):
    tool = open_with_fake_microphone(open_tool)
    page = tool.page
    first_sound(page)
    switch_microphone_on(page)

    # On iOS a context started before the microphone opened hears only zeros.
    assert page.evaluate("() => audioLog") == [
        "new context 1",
        "getUserMedia",
        "close context 1",
        "new context 2",
        "microphone on context 2",
    ]
    if first_sound is start_exercise:
        page.click("#exStop")  # detection is muted while the exercise plays
    open_tab(page, "p-tuner")
    expect(page.locator("#noteName")).to_have_text("A3")
    assert not tool.problems, "\n".join(tool.problems)


def test_a_held_tone_keeps_sounding_when_the_microphone_starts(open_tool):
    tool = open_with_fake_microphone(open_tool)
    page = tool.page
    tap_a3_key(page)
    page.click("#holdTarget")
    switch_microphone_on(page)

    assert page.evaluate("() => heldOsc !== null && heldOsc.osc.context === ctx")
    expect(page.locator("#holdTarget")).to_have_class("ghost on")
    assert not tool.problems, "\n".join(tool.problems)


def test_a_suspended_context_stops_the_readout_until_it_runs_again(open_tool):
    tool = open_with_fake_microphone(open_tool)
    page = tool.page
    switch_microphone_on(page)
    note = page.locator("#noteName")
    expect(note).to_have_text("A3")

    page.evaluate("() => ctx.suspend()")
    expect(note).to_have_text("—")
    expect(page.locator("#micState")).to_have_text(
        "Audio pausiert — kurz auf die Seite tippen."
    )
    newest_point = "() => hist.length ? hist[hist.length - 1].t : null"
    newest_while_paused = page.evaluate(newest_point)
    page.wait_for_timeout(300)
    assert page.evaluate(newest_point) == newest_while_paused

    page.evaluate("() => ctx.resume()")
    expect(page.locator("#micState")).to_have_text("Mikrofon läuft.")
    expect(note).to_have_text("A3")
    assert not tool.problems, "\n".join(tool.problems)


def test_a_context_that_never_starts_shows_the_pause_message(open_tool):
    tool = open_with_fake_microphone(open_tool)
    page = tool.page
    page.evaluate("() => { window.contextNeverRuns = true; }")
    page.click("#micBtn")

    expect(page.locator("#micState")).to_have_text(
        "Audio pausiert — kurz auf die Seite tippen."
    )
    expect(page.locator("#noteName")).to_have_text("—")
    assert not tool.problems, "\n".join(tool.problems)


# --- Manual range ------------------------------------------------------------

LS_KEY = "einsingen-v1"
C4, AIS4 = 60, 70


def set_range_key(page: Page, mode: str, midi: int) -> None:
    page.click(f'#p-umfang [data-mode="{mode}"]')
    page.click(f'#kbRange .key[data-m="{midi}"]')


def range_stat(page: Page, caption: str):
    return page.locator("#rangeStats .stat", has_text=caption).locator(".num")


def saved_ranges(page: Page) -> list[dict]:
    return page.evaluate(f"() => JSON.parse(localStorage.getItem('{LS_KEY}') || '[]')")


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [
        pytest.param(
            ("high", C4),
            ("low", AIS4),
            "Der tiefste Ton kann nicht über dem höchsten (C4) liegen.",
            id="lowest-above-highest",
        ),
        pytest.param(
            ("low", AIS4),
            ("high", C4),
            "Der höchste Ton kann nicht unter dem tiefsten (Ais4) liegen.",
            id="highest-below-lowest",
        ),
    ],
)
def test_manual_range_rejects_an_inverted_range(open_tool, first, second, message):
    tool = open_tool(TOOL, "desktop")
    page = tool.page
    open_tab(page, "p-umfang")
    set_range_key(page, *first)
    set_range_key(page, *second)

    expect(range_stat(page, "Umfang")).to_have_text("–")
    page.click("#saveSession")
    assert saved_ranges(page) == []
    expect(page.locator("#rangeMsg")).to_be_visible()
    expect(page.locator("#rangeMsg")).to_contain_text(message)

    # The same two notes the right way round are a valid range.
    set_range_key(page, "low", C4)
    set_range_key(page, "high", AIS4)
    expect(page.locator("#rangeMsg")).to_be_hidden()
    expect(range_stat(page, "Umfang")).to_have_text("10 Halbtöne")
    page.click("#saveSession")
    assert [(row["low"], row["high"]) for row in saved_ranges(page)] == [(C4, AIS4)]
    assert not tool.problems, "\n".join(tool.problems)
