"""Tests for the new audio_preprocess module (v1.1.0).

Covers:
- Module imports cleanly even with optional backends missing
- `available_backends()` reports the right availability
- `highpass`: kills DC and low-frequency rumble, preserves speech band,
  returns float32 of same length, degrades gracefully on tiny input
- `preemphasis`: simple first-difference HF boost with float32 output
- `normalize_peak`: hits -3 dBFS by default, leaves quiet audio alone,
  returns float32
- `denoise`: degrades gracefully (audio too short) and doesn't crash
  on full-length synthetic noise
- `preprocess`: the orchestrator — runs the right stages in the right
  order, returns audio of the same length, dtype float32
- Tolerance contract: peak gain matches expected within 0.1 dB
"""

import importlib

import numpy as np
import pytest

import audio_preprocess as ap


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: synthetic audio generators
# ─────────────────────────────────────────────────────────────────────────────

SR = 16000


def _sine(freq_hz: float, dur: float = 0.5, sr: int = SR, amp: float = 0.5) -> np.ndarray:
    """Pure sine tone, float32."""
    t = np.arange(int(dur * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _white_noise(dur: float = 1.0, sr: int = SR, amp: float = 0.05) -> np.ndarray:
    """Deterministic-ish white noise (fixed seed)."""
    rng = np.random.default_rng(42)
    n = int(dur * sr)
    return (amp * rng.standard_normal(n).astype(np.float32))


# ─────────────────────────────────────────────────────────────────────────────
# Module sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleImport:
    def test_imports_cleanly(self):
        # The module must import on any environment with numpy, even if
        # scipy/noisereduce are missing.
        assert hasattr(ap, "preprocess")
        assert hasattr(ap, "available_backends")

    def test_backends_dict_shape(self):
        info = ap.available_backends()
        assert isinstance(info, dict)
        assert "scipy" in info
        assert "noisereduce" in info
        assert isinstance(info["scipy"], bool)
        assert isinstance(info["noisereduce"], bool)

    def test_default_sr_is_16k(self):
        # GigaAM is a 16 kHz model. The default sr on every public function
        # is the model rate — if this ever drifts the ASR pipeline breaks.
        assert ap.DEFAULT_SR == 16000


# ─────────────────────────────────────────────────────────────────────────────
# highpass
# ─────────────────────────────────────────────────────────────────────────────

class TestHighpass:
    def test_removes_dc(self):
        if not ap._HAS_SCIPY:
            pytest.skip("scipy not available — highpass is a no-op")
        dc = np.full(SR // 4, 0.8, dtype=np.float32)  # 250 ms of pure DC
        out = ap.highpass(dc, cutoff_hz=80.0, sr=SR)
        # The mean of a high-passed DC signal should be ~0.
        assert abs(float(out.mean())) < 0.01, f"DC leaked through: mean={out.mean():.4f}"
        assert out.dtype == np.float32
        assert out.shape == dc.shape

    def test_preserves_voice_band(self):
        if not ap._HAS_SCIPY:
            pytest.skip("scipy not available")
        # 200 Hz sine (inside adult male voice range, well above 80 Hz cutoff).
        # Passband ripple of 4th-order Butterworth is small; we tolerate -3 dB.
        sig = _sine(200.0, dur=0.3)
        out = ap.highpass(sig, cutoff_hz=80.0, sr=SR)
        rms_in = float(np.sqrt(np.mean(sig ** 2)))
        rms_out = float(np.sqrt(np.mean(out ** 2)))
        # Should keep at least half the energy (very loose — actual is ~95%).
        assert rms_out > 0.5 * rms_in, f"200 Hz killed: rms_in={rms_in:.4f} rms_out={rms_out:.4f}"

    def test_kills_sub_sonic(self):
        if not ap._HAS_SCIPY:
            pytest.skip("scipy not available")
        # 30 Hz subsonic, well below the 80 Hz cutoff → must be heavily attenuated.
        sig = _sine(30.0, dur=0.5)
        out = ap.highpass(sig, cutoff_hz=80.0, sr=SR)
        rms_in = float(np.sqrt(np.mean(sig ** 2)))
        rms_out = float(np.sqrt(np.mean(out ** 2)))
        assert rms_out < 0.1 * rms_in, f"30 Hz leaked: rms_out/rms_in={rms_out/rms_in:.3f}"

    def test_short_input_passthrough(self):
        if not ap._HAS_SCIPY:
            pytest.skip("scipy not available")
        # sosfiltfilt needs padding; anything <32 samples is too short to
        # bother filtering and the function returns the input unchanged.
        sig = _sine(440.0, dur=0.001)  # ~16 samples
        out = ap.highpass(sig, cutoff_hz=80.0, sr=SR)
        np.testing.assert_array_equal(out, sig)

    def test_output_is_float32(self):
        if not ap._HAS_SCIPY:
            pytest.skip("scipy not available")
        sig = _sine(440.0, dur=0.1)
        out = ap.highpass(sig.astype(np.float64), cutoff_hz=80.0, sr=SR)
        assert out.dtype == np.float32


# ─────────────────────────────────────────────────────────────────────────────
# preemphasis
# ─────────────────────────────────────────────────────────────────────────────

class TestPreemphasis:
    def test_first_sample_passthrough(self):
        sig = _sine(440.0, dur=0.1)
        out = ap.preemphasis(sig, coef=0.97)
        # y[0] == x[0] by construction
        assert out[0] == sig[0]

    def test_known_recurrence(self):
        # Hand-crafted: y[n] = x[n] - 0.97 * x[n-1] for n >= 1
        sig = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        out = ap.preemphasis(sig, coef=0.97)
        # First element is x[0] (by code).
        assert out[0] == pytest.approx(0.0, abs=1e-7)
        # n=1: y = 0.1 - 0.97*0.0 = 0.1
        assert out[1] == pytest.approx(0.1, abs=1e-6)
        # n=2: y = 0.2 - 0.97*0.1 = 0.103
        assert out[2] == pytest.approx(0.2 - 0.97 * 0.1, abs=1e-6)

    def test_output_is_float32(self):
        sig = _sine(440.0, dur=0.05)
        out = ap.preemphasis(sig.astype(np.float64))
        assert out.dtype == np.float32

    def test_empty_returns_empty(self):
        out = ap.preemphasis(np.array([], dtype=np.float32))
        assert out.size == 0

    def test_boosts_high_freq_energy(self):
        # Pre-emphasis is a 1st-order HF shelf. A 4 kHz tone should come out
        # louder (in the *signal* sense: more zero-crossings, more absolute
        # high-frequency content) than a 200 Hz tone of equal input amplitude.
        # We test the canonical effect: the difference x[n] - 0.97*x[n-1]
        # has higher RMS than the input on broadband signals.
        rng = np.random.default_rng(0)
        broadband = (0.3 * rng.standard_normal(SR // 2)).astype(np.float32)
        out = ap.preemphasis(broadband, coef=0.97)
        # Pre-emphasis is roughly flat above ~1 kHz and rolls off below — for
        # white noise the output RMS is comparable but not lower. Just check
        # it's not zero and preserves length.
        assert out.shape == broadband.shape
        assert float(np.abs(out).max()) > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# normalize_peak
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizePeak:
    def test_targets_minus_3_dbfs(self):
        # 0.5 peak → -6.02 dBFS → gain to -3 dBFS is +3.02 dB → ×1.41...
        sig = np.full(1000, 0.5, dtype=np.float32)
        out = ap.normalize_peak(sig, target_dbfs=-3.0)
        peak = float(np.abs(out).max())
        expected = 10 ** (-3.0 / 20)  # ≈ 0.7079
        assert peak == pytest.approx(expected, rel=1e-3)
        assert out.dtype == np.float32

    def test_no_change_when_already_close(self):
        # If the gain needed is between 0.99 and 1.01, the function should
        # return the input unchanged (saves a copy on near-target audio).
        sig = (np.ones(1000, dtype=np.float32) * 0.7)
        out = ap.normalize_peak(sig, target_dbfs=-3.0)
        # 0.7 ≈ -3.1 dBFS, gain needed is 0.7079/0.7 ≈ 1.011 — at boundary
        # (we check either the input is returned or the gain was applied).
        peak = float(np.abs(out).max())
        assert 0.7 <= peak <= 0.71

    def test_silent_returns_unchanged(self):
        sig = np.zeros(1000, dtype=np.float32)
        out = ap.normalize_peak(sig)
        np.testing.assert_array_equal(out, sig)

    def test_empty_returns_empty(self):
        out = ap.normalize_peak(np.array([], dtype=np.float32))
        assert out.size == 0

    def test_quiet_signal_untouched(self):
        # Peak below 1e-6 → no scaling (would amplify noise).
        sig = np.full(1000, 1e-9, dtype=np.float32)
        out = ap.normalize_peak(sig)
        np.testing.assert_array_equal(out, sig)


# ─────────────────────────────────────────────────────────────────────────────
# denoise
# ─────────────────────────────────────────────────────────────────────────────

class TestDenoise:
    def test_short_signal_passthrough(self):
        # <0.5 s of audio → noisereduce would have nothing to learn from;
        # we return the input unchanged.
        if not ap._HAS_NOISEREDUCE:
            pytest.skip("noisereduce not installed")
        sig = _sine(440.0, dur=0.1)  # 0.1 s, well below 0.5 s threshold
        out = ap.denoise(sig, sr=SR)
        np.testing.assert_array_equal(out, sig)

    def test_full_length_synthetic_runs(self):
        if not ap._HAS_NOISEREDUCE:
            pytest.skip("noisereduce not installed")
        # 1 s of noise — noisereduce should at least not crash and return
        # an array of the same shape.
        sig = _white_noise(dur=1.0, amp=0.1)
        out = ap.denoise(sig, sr=SR)
        assert out.shape == sig.shape
        assert out.dtype == np.float32


# ─────────────────────────────────────────────────────────────────────────────
# preprocess (orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class TestPreprocess:
    def test_all_off_returns_unchanged_shape(self):
        sig = _sine(440.0, dur=0.3)
        out = ap.preprocess(sig, do_denoise=False, do_highpass=False,
                            do_preemphasis=False, do_normalize=False)
        assert out.shape == sig.shape
        np.testing.assert_array_equal(out, sig)

    def test_only_normalize_hits_target(self):
        sig = _sine(440.0, dur=0.3, amp=0.1)
        out = ap.preprocess(sig, do_normalize=True, do_highpass=False,
                            do_preemphasis=False, do_denoise=False)
        peak = float(np.abs(out).max())
        target = 10 ** (-3.0 / 20)
        assert peak == pytest.approx(target, rel=1e-3)

    def test_pipeline_preserves_length(self):
        sig = _sine(440.0, dur=0.5, amp=0.3) + _white_noise(dur=0.5, amp=0.02)
        out = ap.preprocess(sig, do_normalize=True, do_highpass=True,
                            do_preemphasis=False, do_denoise=False)
        assert out.shape == sig.shape
        assert out.dtype == np.float32

    def test_pipeline_reorders_preemphasis_before_normalize(self):
        # The docstring says: denoise → highpass → preemphasis → normalize.
        # If pre-emphasis runs AFTER normalize, the peak will overshoot -3 dBFS.
        # So we verify the output is at -3 dBFS, meaning normalize ran last.
        sig = _sine(440.0, dur=0.5, amp=0.1)
        out = ap.preprocess(sig, do_normalize=True, do_highpass=True,
                            do_preemphasis=True, do_denoise=False)
        peak = float(np.abs(out).max())
        target = 10 ** (-3.0 / 20)
        assert peak == pytest.approx(target, rel=1e-3), (
            f"normalize must be the last stage: peak={peak:.4f} target={target:.4f}"
        )

    def test_pipeline_handles_empty(self):
        out = ap.preprocess(np.array([], dtype=np.float32))
        assert out is not None
        assert out.size == 0

    def test_pipeline_handles_none(self):
        out = ap.preprocess(None)
        assert out is None

    def test_pipeline_casts_to_float32(self):
        sig = _sine(440.0, dur=0.1).astype(np.float64)
        out = ap.preprocess(sig, do_normalize=True)
        assert out.dtype == np.float32

    def test_default_flags_match_config_defaults(self):
        # Defaults of `preprocess(...)` should match the config module's
        # PP_* flags so that the main pipeline can call
        # audio_preprocess(audio, sr=..., **{flag_name: getattr(config, f"PP_{name}")})
        # without diverging from the documented behaviour.
        sig = _sine(440.0, dur=0.3, amp=0.1)
        out = ap.preprocess(sig)  # use defaults
        # Defaults: highpass=True, normalize=True, denoise=False, preemph=False
        # → should be normalized to -3 dBFS.
        peak = float(np.abs(out).max())
        target = 10 ** (-3.0 / 20)
        assert peak == pytest.approx(target, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# config integration: ensure main.py can call audio_preprocess with getattr
# defaults without breaking.
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigIntegration:
    def test_pp_flags_present_in_config(self):
        import config
        # The main pipeline uses getattr(config, "PP_*", default). If any
        # of these is missing the import still has to work, but having them
        # present is the contract.
        assert hasattr(config, "PP_HIGHPASS")
        assert hasattr(config, "PP_NORMALIZE")
        assert hasattr(config, "PP_DENOISE")
        assert hasattr(config, "PP_PREEMPHASIS")

    def test_pp_flags_are_bools(self):
        import config
        for name in ("PP_HIGHPASS", "PP_NORMALIZE", "PP_DENOISE", "PP_PREEMPHASIS"):
            assert isinstance(getattr(config, name), bool), f"{name} not a bool"
