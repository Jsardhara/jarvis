"""Authority gate tests."""
from __future__ import annotations

import pytest

from jarvis.core.authority import AuthorityError, check_authority, requires_confirm


def test_tier_1_always_requires_confirm():
    assert requires_confirm("tempo", "send_mail", tier=1)
    assert requires_confirm("atlas", "trader_execute", tier=1)
    assert requires_confirm("forge", "push", tier=1)


def test_tier_2_external_actions_require_confirm():
    assert requires_confirm("tempo", "send_mail", tier=2)
    assert requires_confirm("atlas", "trader_execute", tier=2)
    assert requires_confirm("tempo", "cancel", tier=2)


def test_tier_2_internal_actions_dont_require():
    assert not requires_confirm("tempo", "fetch", tier=2)
    assert not requires_confirm("lens", "search", tier=2)


def test_tier_3_5_external_actions_still_confirm():
    assert requires_confirm("tempo", "send_mail", tier=3)
    assert requires_confirm("tempo", "send_mail", tier=5)
    assert requires_confirm("atlas", "trader_execute", tier=4)


def test_tier_3_5_internal_actions_dont_confirm():
    assert not requires_confirm("tempo", "fetch", tier=3)
    assert not requires_confirm("lens", "search", tier=4)
    assert not requires_confirm("forge", "read", tier=5)


def test_check_authority_passes_when_confirmed():
    check_authority("tempo", "send_mail", tier=1, confirmed=True)
    check_authority("atlas", "trader_execute", tier=2, confirmed=True)


def test_check_authority_raises_when_not_confirmed():
    with pytest.raises(AuthorityError) as exc_info:
        check_authority("tempo", "send_mail", tier=1, confirmed=False)
    assert "tier-1" in str(exc_info.value)


def test_check_authority_raises_tier_2_external_without_confirm():
    with pytest.raises(AuthorityError) as exc_info:
        check_authority("tempo", "send_mail", tier=2, confirmed=False)
    assert "tier-2" in str(exc_info.value)
    assert "external" in str(exc_info.value)


def test_check_authority_passes_tier_2_internal_without_confirm():
    check_authority("tempo", "fetch", tier=2, confirmed=False)


def test_authority_error_has_action_and_reason():
    try:
        check_authority("tempo", "send_mail", tier=1, confirmed=False)
    except AuthorityError as e:
        assert e.action == "send_mail"
        assert e.reason
        assert "tier-1" in e.reason
