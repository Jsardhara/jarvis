"""Unit tests for classify_llm — mock Anthropic, success path, fallback, cache, cost."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from jarvis.contract import IntentClassification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_anthropic_response(primary: str, parallel: list[str], rationale: str, confidence: float) -> MagicMock:
    """Return a mock anthropic.types.Message with the given classification JSON."""
    import json

    content_block = MagicMock()
    content_block.text = json.dumps(
        {
            "primary": primary,
            "parallel": parallel,
            "rationale": rationale,
            "confidence": confidence,
        }
    )
    msg = MagicMock()
    msg.content = [content_block]
    msg.usage.input_tokens = 120
    msg.usage.output_tokens = 40
    return msg


# ---------------------------------------------------------------------------
# classify_llm: success path
# ---------------------------------------------------------------------------


def test_classify_llm_returns_intent_classification():
    """classify_llm returns an IntentClassification when Anthropic responds correctly."""
    from jarvis.router import classify_llm

    mock_resp = _make_anthropic_response("tempo", [], "matched email keyword", 0.95)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            result = classify_llm("check my email")

    assert isinstance(result, IntentClassification)
    assert result.primary == "tempo"
    assert result.confidence == pytest.approx(0.95)
    assert result.rationale == "matched email keyword"


def test_classify_llm_parallel_agents_populated():
    """classify_llm populates parallel list for multi-domain responses."""
    from jarvis.router import classify_llm

    mock_resp = _make_anthropic_response(
        "tempo", ["scholar", "atlas"], "morning briefing", 0.9
    )

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            result = classify_llm("morning briefing")

    assert result.primary == "tempo"
    assert "scholar" in result.parallel
    assert "atlas" in result.parallel


def test_classify_llm_unknown_primary_falls_back_to_regex():
    """classify_llm falls back to regex classify when LLM returns an unknown agent name."""
    from jarvis.router import classify_llm

    mock_resp = _make_anthropic_response("unknown_agent", [], "bad parse", 0.5)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            result = classify_llm("check my email")

    # Should fall back: "check my email" → tempo via regex
    assert result.primary == "tempo"


# ---------------------------------------------------------------------------
# classify_llm: failure → fallback
# ---------------------------------------------------------------------------


def test_classify_llm_falls_back_on_api_error():
    """When Anthropic raises an exception, classify_llm falls back to regex classify."""
    from jarvis.router import classify_llm

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = RuntimeError("network error")

            result = classify_llm("check my email")

    # Fallback regex: "check my email" → tempo
    assert result.primary == "tempo"
    assert isinstance(result, IntentClassification)


def test_classify_llm_falls_back_on_json_parse_error():
    """When LLM returns non-JSON text, classify_llm falls back to regex."""
    from jarvis.router import classify_llm

    content_block = MagicMock()
    content_block.text = "Sorry, I cannot classify that."
    bad_msg = MagicMock()
    bad_msg.content = [content_block]
    bad_msg.usage.input_tokens = 100
    bad_msg.usage.output_tokens = 20

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = bad_msg

            result = classify_llm("when is my cs501 assignment due")

    assert result.primary == "scholar"


def test_classify_llm_falls_back_on_missing_field():
    """When LLM JSON omits required fields, classify_llm falls back to regex."""
    import json

    from jarvis.router import classify_llm

    content_block = MagicMock()
    content_block.text = json.dumps({"primary": "tempo"})  # missing confidence etc.
    partial_msg = MagicMock()
    partial_msg.content = [content_block]
    partial_msg.usage.input_tokens = 80
    partial_msg.usage.output_tokens = 15

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = partial_msg

            result = classify_llm("check my email")

    assert isinstance(result, IntentClassification)


# ---------------------------------------------------------------------------
# classify_llm: cost logging
# ---------------------------------------------------------------------------


def test_classify_llm_logs_cost_on_success():
    """classify_llm calls log_cost with correct agent and model on success."""
    from jarvis.router import classify_llm

    mock_resp = _make_anthropic_response("lens", [], "research", 0.88)
    mock_resp.usage.input_tokens = 150
    mock_resp.usage.output_tokens = 35

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("jarvis.router.anthropic") as mock_module:
            with patch("jarvis.router.log_cost") as mock_log:
                mock_client = MagicMock()
                mock_module.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_resp

                classify_llm("research transformers")

    mock_log.assert_called_once_with(
        agent="jarvis-router",
        model="claude-haiku-4-5-20251001",
        in_tokens=150,
        out_tokens=35,
    )


# ---------------------------------------------------------------------------
# Top-level classify: LLM switch
# ---------------------------------------------------------------------------


def test_classify_uses_llm_when_key_set_and_switch_on():
    """classify() delegates to classify_llm when ANTHROPIC_API_KEY is set and switch is on."""
    from jarvis import router

    mock_resp = _make_anthropic_response("forge", [], "code task", 0.92)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(router, "USE_LLM_ROUTER", True):
            with patch("jarvis.router.anthropic") as mock_module:
                mock_client = MagicMock()
                mock_module.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_resp

                result = router.classify("refactor auth module")

    assert result.primary == "forge"


def test_classify_uses_regex_when_no_api_key():
    """classify() uses regex fallback when ANTHROPIC_API_KEY is absent."""
    from jarvis import router

    with patch.dict(os.environ, {}, clear=True):
        # Remove key if present
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(router, "USE_LLM_ROUTER", True):
                result = router.classify("check my email")

    assert result.primary == "tempo"


def test_classify_uses_regex_when_switch_off():
    """classify() skips LLM entirely when USE_LLM_ROUTER=False."""
    from jarvis import router

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(router, "USE_LLM_ROUTER", False):
            with patch("jarvis.router.classify_llm") as mock_llm:
                result = router.classify("check my email")

    mock_llm.assert_not_called()
    assert result.primary == "tempo"
