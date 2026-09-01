"""Unit tests for asr_engine._stitch_overlap_texts (no model needed)."""
import numpy as np
import pytest


class TestStitchOverlap:
    """Tests for _stitch_overlap_texts — joining overlapping ASR pieces."""

    def test_single_piece_unchanged(self):
        from asr_engine import _stitch_overlap_texts
        assert _stitch_overlap_texts(["привет мир"], overlap_samples=0, sr=16000) == "привет мир"

    def test_empty_list(self):
        from asr_engine import _stitch_overlap_texts
        assert _stitch_overlap_texts([], overlap_samples=0, sr=16000) == ""

    def test_list_of_empty_strings(self):
        from asr_engine import _stitch_overlap_texts
        assert _stitch_overlap_texts(["", ""], overlap_samples=0, sr=16000) == ""

    def test_two_pieces_no_overlap_words(self):
        """When there's no shared word, just space-join."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(["привет мир", "как дела"], overlap_samples=0, sr=16000)
        assert result == "привет мир как дела"

    def test_two_pieces_with_overlap(self):
        """Boundary word 'тест' is duplicated and should be deduped."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["это простой тест", "тест на стыковку"], overlap_samples=0, sr=16000
        )
        assert result == "это простой тест на стыковку"

    def test_three_pieces_chain(self):
        """Chained overlap across 3 pieces — all duplicates removed."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["я говорю про тест", "тест очень важен", "важен для дела"],
            overlap_samples=0, sr=16000,
        )
        assert result == "я говорю про тест очень важен для дела"

    def test_multi_word_overlap(self):
        """Overlap spanning multiple words — prefer longest match."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["раз два три четыре", "три четыре пять шесть"],
            overlap_samples=0, sr=16000,
        )
        # Both "три четыре" (2 words) and "четыре" (1 word) match; LCP picks 2.
        assert result == "раз два три четыре пять шесть"

    def test_punctuation_whitespace_normalized(self):
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["  привет   мир  ", "мир   как    дела  "],
            overlap_samples=0, sr=16000,
        )
        # Whitespace is collapsed; 'мир' is shared, so only kept once.
        assert "привет" in result
        assert "как дела" in result
        # No double "мир"
        assert result.count("мир") == 1

    def test_overlap_is_substring_not_subsequence(self):
        """'abc' and 'bc' should NOT match (suffix/prefix, not subsequence)."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["один abc", "bc два"], overlap_samples=0, sr=16000
        )
        # "bc" is a prefix of "bc два" but NOT a suffix of "один abc" as a whole word
        # so no dedup, space-join
        assert result == "один abc bc два"

    # ── regression tests: decoder restarts a "sentence" at slice boundary ──
    #
    # The ASR decoder capitalises the first word of each slice and ends the
    # previous slice with a full stop, so raw token comparison misses the
    # overlap and the tail slice gets duplicated wholesale ("...и нашёл
    # И нашёл...", "...только планируем. Только планируем.").

    def test_case_insensitive_overlap_keeps_original(self):
        """'и нашёл' duplicated with capital I should dedup; original kept."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["чтобы ты проанализировал и нашёл", "И нашёл потенциальную причину"],
            overlap_samples=16000, sr=16000,  # 1s overlap
        )
        assert result == "чтобы ты проанализировал и нашёл потенциальную причину"

    def test_first_word_punct_insensitive(self):
        """Piece 1 ends with a comma glued to the word; piece 2 starts with
        a comma-glued copy too — still dedup."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["я говорю", "говорю, что надо"],
            overlap_samples=16000, sr=16000,
        )
        assert result == "я говорю что надо"

    def test_tail_slice_fully_repeated(self):
        """The whole tail slice repeats the previous boundary (e.g. 1-2s
        slice of 'Только планируем.'). Must collapse to a single copy."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["Только планируем", "Только планируем."],
            overlap_samples=16000, sr=16000,
        )
        assert result == "Только планируем"

    def test_final_word_with_stop_dot_dedup(self):
        """'то есть' / 'То есть голос...' — the exact 'То есть То есть' log case."""
        from asr_engine import _stitch_overlap_texts
        result = _stitch_overlap_texts(
            ["но то есть", "То есть голос записывает"],
            overlap_samples=16000, sr=16000,
        )
        assert result == "но то есть голос записывает"

    def test_overlap_cap_guards_against_overeating(self):
        """Overlap cap derives from the real overlap duration: with 1s of
        overlap (~4-6 words) an 8-word repeated tail looks like a model
        hallucination rather than real duplicated audio — so the cap must
        stop the LCP from eating genuine content beyond the physical
        overlap. With 3s of overlap the same 8-word repeat fits inside the
        window and is deduped normally."""
        from asr_engine import _stitch_overlap_texts
        a = "раз два три четыре пять шесть семь восемь девять десять одиннадцать"
        b = "четыре пять шесть семь восемь девять десять одиннадцать ещё"
        # 1s overlap -> cap = max(4, 4+2) = 6: the shared 8-word span
        # exceeds the cap, no k matches, so nothing is eaten (b joined as is).
        result = _stitch_overlap_texts([a, b], overlap_samples=16000, sr=16000)
        assert result == (
            "раз два три четыре пять шесть семь восемь девять десять одиннадцать "
            "четыре пять шесть семь восемь девять десять одиннадцать ещё"
        )
        # 3s overlap -> cap = max(4, 12+2) = 14: 8-word span fits, deduped.
        result = _stitch_overlap_texts([a, b], overlap_samples=48000, sr=16000)
        assert result == "раз два три четыре пять шесть семь восемь девять десять одиннадцать ещё"


class TestOverlapSliceConstants:
    """Tests for the overlap-slicing threshold and tail-pad configuration."""

    def test_slice_seconds_lowered_to_4(self):
        """_SLICE_SECONDS was lowered from 6 to 4 so 4-7s utterances also slice."""
        from asr_engine import GigaAMEngine
        assert GigaAMEngine._SLICE_SECONDS == 4

    def test_tail_pad_seconds_defined(self):
        """_TAIL_PAD_SECONDS is a small positive float (silence padding)."""
        from asr_engine import GigaAMEngine
        v = GigaAMEngine._TAIL_PAD_SECONDS
        assert isinstance(v, (int, float))
        assert 0.1 <= v <= 1.0, f"tail pad should be small, got {v}"

    def test_chunk_seconds_unchanged(self):
        """_CHUNK_SECONDS still 30 — long audio chunk boundary."""
        from asr_engine import GigaAMEngine
        assert GigaAMEngine._CHUNK_SECONDS == 30


class TestOverlapSlicePadding:
    """Tests that GigaAMEngine._transcribe_overlap_locked appends silence
    padding so the CTC decoder doesn't swallow the trailing words. We
    don't load the real model; we install a fake _asr on a fresh engine
    and inspect the audio it received."""

    @staticmethod
    def _make_engine_with_fake_asr(captured: list):
        """Build a GigaAMEngine-like object with a fake _asr.recognize that
        records the audio it received, and bypass _load_locked (no real
        model). Returns the engine."""
        from asr_engine import GigaAMEngine

        class FakeEngine(GigaAMEngine):
            def __init__(self):
                self._asr = type("F", (), {})()
                self._lock = __import__("threading").RLock()
                self._sample_rate = 16000
                self._loaded_spec = object()  # non-None so _load_locked is skipped
                self._spec = object()

            def _load_locked(self):  # no-op, model is "loaded"
                return

        eng = FakeEngine()

        def fake_recognize(audio, sample_rate):
            captured.append(np.asarray(audio).copy())
            return "fake"

        eng._asr.recognize = fake_recognize
        return eng

    def test_short_audio_gets_tail_pad(self):
        """Audio shorter than _SLICE_SECONDS must still be padded with silence."""
        import numpy as np
        from asr_engine import GigaAMEngine

        captured = []
        eng = self._make_engine_with_fake_asr(captured)

        # 2.0 s of audio @ 16 kHz = 32000 samples
        audio = np.ones(32000, dtype=np.float32)
        eng._transcribe_overlap_locked(audio)

        # The fake ASR should have received the original audio PLUS a
        # silence tail. Expected length: 32000 + tail_pad_samples.
        assert len(captured) == 1, "expected exactly one recognize() call"
        sent = captured[0]
        tail_pad_samples = int(GigaAMEngine._TAIL_PAD_SECONDS * 16000)
        assert len(sent) == 32000 + tail_pad_samples, (
            f"expected audio + {tail_pad_samples} samples of tail pad, "
            f"got {len(sent)} total"
        )
        # Tail pad should be silent (zeros)
        np.testing.assert_array_equal(sent[32000:], np.zeros(tail_pad_samples))

    def test_multi_slice_audio_each_gets_pad(self):
        """Each slice in multi-slice mode is padded with the same silence tail."""
        import numpy as np
        from asr_engine import GigaAMEngine

        captured = []
        eng = self._make_engine_with_fake_asr(captured)

        # 8.0 s of audio @ 16 kHz = 128000 samples. > _SLICE_SECONDS so
        # slicing kicks in.
        audio = np.ones(128000, dtype=np.float32)
        eng._transcribe_overlap_locked(audio)

        # We expect at least 2 slices, each padded.
        assert len(captured) >= 2, f"expected ≥2 slices, got {len(captured)}"
        slice_len_samples = int(GigaAMEngine._SLICE_SECONDS * 16000)
        tail_pad_samples = int(GigaAMEngine._TAIL_PAD_SECONDS * 16000)
        for idx, sent in enumerate(captured):
            # The body of the slice (before tail pad) is no longer than
            # slice_len_samples; the total includes the pad.
            assert len(sent) <= slice_len_samples + tail_pad_samples, (
                f"slice {idx} too long: {len(sent)}"
            )
            # The tail of each slice is zero (the silence pad).
            tail_len = tail_pad_samples
            np.testing.assert_array_equal(sent[-tail_len:], np.zeros(tail_len))
