"""einsingen.html: regression tests for issue #14.

The pitch tests synthesize their own tones and feed them to the page's
``detectPitch`` exactly as the measuring loop does: one analyser window of
``pickFftSize(sampleRate)`` samples and the gate at the default sensitivity.
The expected note is the one the tone was built from, never a value the page
computes.
"""

import math

import pytest

TOOL = "einsingen.html"

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
