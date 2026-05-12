"""Tests for OpenWakeWordDetector — pretrained 'hey jarvis' wake-word.

Mocks the openwakeword package so tests don't download models or require the
extra. Verifies the listen() loop, threshold gating, and ImportError surface.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fake openwakeword package
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_openwakeword(monkeypatch):
    """Inject a mock openwakeword package into sys.modules."""
    pkg = types.ModuleType("openwakeword")
    model_mod = types.ModuleType("openwakeword.model")
    utils_mod = types.ModuleType("openwakeword.utils")

    fake_model_instance = MagicMock()
    fake_model_instance.predict = MagicMock(return_value={"hey_jarvis_v0.1": 0.0})
    model_mod.Model = MagicMock(return_value=fake_model_instance)
    utils_mod.download_models = MagicMock(return_value=None)

    pkg.model = model_mod
    pkg.utils = utils_mod
    monkeypatch.setitem(sys.modules, "openwakeword", pkg)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_mod)
    monkeypatch.setitem(sys.modules, "openwakeword.utils", utils_mod)
    return fake_model_instance


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def test_init_stores_threshold_and_keyword(fake_openwakeword):
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(model_name="hey_jarvis_v0.1", threshold=0.7)
    assert det.threshold == 0.7
    assert det.keyword == "hey jarvis"


def test_init_keyword_strips_version_suffix(fake_openwakeword):
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(model_name="custom_model_v0.1")
    assert det.keyword == "custom model"


def test_init_tolerates_download_failure(fake_openwakeword, monkeypatch):
    """download_models exception is logged + swallowed."""
    import openwakeword.utils

    def boom(_models):
        raise RuntimeError("offline")

    monkeypatch.setattr(openwakeword.utils, "download_models", boom)
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector()  # should not raise
    assert det.keyword == "hey jarvis"


def test_init_raises_when_openwakeword_missing(monkeypatch):
    """No openwakeword installed → RuntimeError with install hint."""
    monkeypatch.setitem(sys.modules, "openwakeword", None)
    monkeypatch.setitem(sys.modules, "openwakeword.model", None)
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    with pytest.raises(RuntimeError, match="openwakeword not installed"):
        OpenWakeWordDetector()


# ---------------------------------------------------------------------------
# listen()
# ---------------------------------------------------------------------------

def _chunk(samples: int = 480, value: int = 1000) -> bytes:
    """480 int16 samples = 30ms @ 16kHz."""
    return np.full(samples, value, dtype=np.int16).tobytes()


def test_listen_returns_true_when_score_meets_threshold(fake_openwakeword):
    fake_openwakeword.predict = MagicMock(return_value={"hey_jarvis_v0.1": 0.9})
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(threshold=0.5)
    assert det.listen([_chunk()]) is True


def test_listen_returns_false_when_score_below_threshold(fake_openwakeword):
    fake_openwakeword.predict = MagicMock(return_value={"hey_jarvis_v0.1": 0.1})
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(threshold=0.5)
    assert det.listen([_chunk(), _chunk()]) is False


def test_listen_skips_empty_chunks(fake_openwakeword):
    fake_openwakeword.predict = MagicMock(return_value={"hey_jarvis_v0.1": 0.0})
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector()
    # empty bytes → arr.size == 0 → continue (no predict call)
    assert det.listen([b""]) is False
    fake_openwakeword.predict.assert_not_called()


def test_listen_returns_true_on_first_qualifying_chunk(fake_openwakeword):
    """Predict returns 0.1 then 0.9 — should stop after second chunk."""
    seq = [{"hey_jarvis_v0.1": 0.1}, {"hey_jarvis_v0.1": 0.9}, {"hey_jarvis_v0.1": 0.95}]
    fake_openwakeword.predict = MagicMock(side_effect=seq)
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(threshold=0.5)
    assert det.listen([_chunk(), _chunk(), _chunk()]) is True
    # only first two chunks consumed
    assert fake_openwakeword.predict.call_count == 2


def test_listen_handles_threshold_boundary(fake_openwakeword):
    """score == threshold → True (>=)."""
    fake_openwakeword.predict = MagicMock(return_value={"hey_jarvis_v0.1": 0.5})
    from jarvis.apps.voice.openwakeword_detector import OpenWakeWordDetector

    det = OpenWakeWordDetector(threshold=0.5)
    assert det.listen([_chunk()]) is True


def test_module_exports():
    from jarvis.apps.voice import openwakeword_detector

    assert "OpenWakeWordDetector" in openwakeword_detector.__all__
    assert openwakeword_detector.DEFAULT_MODEL == "hey_jarvis_v0.1"
    assert openwakeword_detector.DEFAULT_THRESHOLD == 0.5
