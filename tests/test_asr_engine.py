"""Unit tests for asr_engine.py — GigaAM v3 E2E CTC via onnx-asr."""
import numpy as np
import pytest


class TestGigaAMEngine:
    """Tests for GigaAMEngine class."""

    def test_engine_name(self):
        """GigaAMEngine exists and is a class."""
        from asr_engine import GigaAMEngine
        assert GigaAMEngine.__name__ == "GigaAMEngine"

    def test_engine_has_transcribe_method(self):
        """GigaAMEngine has a transcribe method."""
        from asr_engine import GigaAMEngine
        engine = GigaAMEngine()
        assert hasattr(engine, "transcribe")
        assert callable(engine.transcribe)

    def test_engine_has_load_unload(self):
        """Engine has load() and unload() lifecycle methods."""
        from asr_engine import GigaAMEngine
        engine = GigaAMEngine()
        assert callable(engine.load)
        assert callable(engine.unload)

    def test_engine_has_warmup(self):
        """Engine has warmup() method for ONNX session JIT."""
        from asr_engine import GigaAMEngine
        engine = GigaAMEngine()
        assert callable(engine.warmup)

    def test_engine_initially_not_loaded(self):
        """Engine has no model loaded on construction."""
        from asr_engine import GigaAMEngine
        engine = GigaAMEngine()
        assert engine._asr is None

    def test_load_twice_is_noop(self):
        """Calling load() twice does not reload."""
        import asr_engine
        # Mock _load_onnx_asr to track calls
        load_count = [0]
        original_load = asr_engine._load_onnx_asr

        class FakeONNX:
            def load_model(self, *a, **kw):
                load_count[0] += 1
                m = type("M", (), {"recognize": lambda s, audio, **k: ""})()
                return m

        asr_engine._load_onnx_asr = lambda: FakeONNX()
        try:
            engine = asr_engine.GigaAMEngine()
            engine.load()
            first = load_count[0]
            engine.load()  # second call
            assert load_count[0] == first, "load() should be idempotent"
        finally:
            asr_engine._load_onnx_asr = original_load

    def test_unload_when_not_loaded(self):
        """unload() on fresh engine is a no-op (doesn't raise)."""
        from asr_engine import GigaAMEngine
        engine = GigaAMEngine()
        engine.unload()  # should not raise
        assert engine._asr is None

    def test_transcribe_raises_when_model_load_fails(self):
        """transcribe() raises if model loading fails."""
        import asr_engine
        original = asr_engine._load_onnx_asr
        asr_engine._load_onnx_asr = lambda: (_ for _ in ()).throw(
            ImportError("onnx_asr not installed")
        )
        try:
            engine = asr_engine.GigaAMEngine()
            audio = np.zeros(16000, dtype=np.float32)
            with pytest.raises(ImportError):
                engine.transcribe(audio)
        finally:
            asr_engine._load_onnx_asr = original


class TestCreateEngine:
    """Tests for the singleton create_engine() factory."""

    def test_create_engine_returns_gigaam_engine(self):
        """create_engine() returns a GigaAMEngine instance."""
        import asr_engine
        engine = asr_engine.create_engine()
        assert isinstance(engine, asr_engine.GigaAMEngine)

    def test_create_engine_returns_same_instance(self):
        """create_engine() is a singleton — returns the same object."""
        import asr_engine
        e1 = asr_engine.create_engine()
        e2 = asr_engine.create_engine()
        assert e1 is e2

    def test_engine_singleton_after_unload(self):
        """After unload(), create_engine() still returns same singleton."""
        import asr_engine
        e1 = asr_engine.create_engine()
        e1.unload()
        e2 = asr_engine.create_engine()
        assert e1 is e2


# NOTE: TranscriptionResult dataclass was removed in 1.1.0 audit fixes
# — it was never imported by the production pipeline. If a future change
# reintroduces a structured result type, add a new test class here.


class TestCudaDllPaths:
    """Tests for _register_cuda_dll_paths()."""

    def test_register_cuda_dll_paths_runs(self):
        """_register_cuda_dll_paths() does not raise."""
        from asr_engine import _register_cuda_dll_paths
        _register_cuda_dll_paths()  # should not raise

    def test_register_cuda_dll_paths_idempotent(self):
        """Calling _register_cuda_dll_paths() twice does not raise."""
        from asr_engine import _register_cuda_dll_paths
        _register_cuda_dll_paths()
        _register_cuda_dll_paths()  # should not raise


class TestInt8ModelDir:
    """Tests for _int8_model_dir()."""

    def test_int8_model_dir_returns_string(self):
        """_int8_model_dir() returns a string path."""
        from asr_engine import _int8_model_dir
        path = _int8_model_dir()
        assert isinstance(path, str)
        assert len(path) > 0
