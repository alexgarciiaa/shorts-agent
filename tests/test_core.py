"""Unit tests for pure pipeline logic (no network / no ffmpeg)."""
import math

from shorts_agent.motion.captions import (chunk_caption, chunks_from_timings,
                                           _is_emphasis)
from shorts_agent.pipeline import _hash, _slug


def test_chunk_caption_covers_full_duration():
    chunks = chunk_caption("one two three four five", total_duration=5.0,
                           words_per_chunk=1)
    assert len(chunks) == 5
    assert chunks[0][1] == 0.0
    # last chunk ends exactly at the total duration
    assert math.isclose(chunks[-1][2], 5.0, rel_tol=1e-6)
    # chunks are contiguous and ordered
    for (_, _, end), (_, start, _) in zip(chunks, chunks[1:]):
        assert math.isclose(end, start, rel_tol=1e-6)


def test_chunk_caption_multiword():
    chunks = chunk_caption("a b c d", total_duration=4.0, words_per_chunk=2)
    assert [c[0] for c in chunks] == ["a b", "c d"]


def test_chunk_caption_empty():
    assert chunk_caption("", 3.0) == []


def test_is_emphasis_numbers_power_words_and_long_words():
    assert _is_emphasis("5,000")
    assert _is_emphasis("BILLION")
    assert _is_emphasis("most")           # power word, case-insensitive
    assert _is_emphasis("planet")         # content word >= 5 letters -> highlighted
    assert not _is_emphasis("the")        # short function word
    assert not _is_emphasis("your")       # short function word
    assert not _is_emphasis("which")      # long but a stopword


def test_chunks_from_timings_uses_real_times():
    timings = [("A", 0.0, 0.2), ("day", 0.2, 0.5), ("on", 0.5, 0.7), ("Venus", 0.7, 1.1)]
    chunks = chunks_from_timings(timings, words_per_chunk=2, total_duration=1.3)
    assert chunks[0] == ("A day", 0.0, 0.5)
    assert chunks[1][0] == "on Venus"
    assert chunks[1][1] == 0.5            # starts exactly when "on" is spoken
    assert chunks[-1][2] >= 1.1           # extends to ~end


def test_chunks_from_timings_empty():
    assert chunks_from_timings([], 1) == []


def test_slug_is_filesystem_safe():
    assert _slug("7 Space Facts That Sound FAKE! \U0001f92f") == "7-space-facts-that-sound-fake"
    assert _slug("") == "short"
    s = _slug("¿Sabías esto?")
    assert " " not in s and s             # non-ascii handled, never empty


def test_hash_is_deterministic_and_sensitive():
    assert _hash("a", "b") == _hash("a", "b")
    assert _hash("a", "b") != _hash("a", "c")
    assert len(_hash("x")) == 12
