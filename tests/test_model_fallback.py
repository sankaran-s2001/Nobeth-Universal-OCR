"""Unit tests for Gemini automated model fallback and failover resilience."""

from unittest.mock import MagicMock
import pytest

from services.gemini_service import (
    GeminiService,
    get_gemini_model_id,
    get_gemini_fallback_model_id,
)


def test_default_model_ids():
    assert get_gemini_model_id() == "gemini-3.1-flash-lite"
    assert get_gemini_fallback_model_id() == "gemini-3.5-flash-lite"


def test_primary_model_success():
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")
    
    mock_call = MagicMock(return_value="primary_success")
    
    result = service._execute_with_failover(
        mock_call,
        op_id="TEST-FAILOVER-1",
    )
    
    assert result == "primary_success"
    assert service.active_model_id == "gemini-3.1-flash-lite"
    assert service.is_fallback_active is False
    mock_call.assert_called_once_with("gemini-3.1-flash-lite")


def test_failover_to_fallback_on_503_high_demand():
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")
    
    switched_models = []

    def on_switch(new_model):
        switched_models.append(new_model)

    def mock_call(model_name):
        if model_name == "gemini-3.1-flash-lite":
            raise RuntimeError("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}")
        elif model_name == "gemini-3.5-flash-lite":
            return "fallback_success"
        raise ValueError(f"Unexpected model: {model_name}")

    result = service._execute_with_failover(
        mock_call,
        op_id="TEST-FAILOVER-2",
        on_model_switch=on_switch,
    )

    assert result == "fallback_success"
    assert service.active_model_id == "gemini-3.5-flash-lite"
    assert service.is_fallback_active is True
    assert switched_models == ["gemini-3.5-flash-lite"]


def test_failover_to_fallback_on_429_quota():
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")

    def mock_call(model_name):
        if model_name == "gemini-3.1-flash-lite":
            raise RuntimeError("429 Resource Exhausted. Quota exceeded for model gemini-3.1-flash-lite")
        return "fallback_recovered"

    result = service._execute_with_failover(
        mock_call,
        op_id="TEST-FAILOVER-3",
    )

    assert result == "fallback_recovered"
    assert service.active_model_id == "gemini-3.5-flash-lite"
    assert service.is_fallback_active is True


def test_fatal_auth_error_does_not_failover():
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")

    def mock_call(model_name):
        raise RuntimeError("401 UNAUTHENTICATED. API key not valid")

    with pytest.raises(ValueError, match="authentication failed"):
        service._execute_with_failover(mock_call, op_id="TEST-FAILOVER-4")


def test_failover_on_504_deadline_exceeded():
    """Verify that 504 DEADLINE_EXCEEDED triggers immediate failover to the fallback model."""
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")
    attempts = []

    def mock_call(model_name):
        attempts.append(model_name)
        if model_name == "gemini-3.1-flash-lite":
            raise RuntimeError("504 DEADLINE_EXCEEDED. {'error': {'code': 504, 'message': 'Deadline expired before operation could complete.', 'status': 'DEADLINE_EXCEEDED'}}")
        return "fallback_after_504"

    result = service._execute_with_failover(mock_call, op_id="TEST-FAILOVER-504")

    assert result == "fallback_after_504"
    assert attempts == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    assert service.active_model_id == "gemini-3.5-flash-lite"
    assert service.is_fallback_active is True


def test_alternating_ping_pong_failover():
    """
    Verify alternating ping-pong pattern:
    Attempt 1 (M1) fails -> Attempt 2 (M2) fails -> Attempt 3 (M1) succeeds!
    """
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")
    call_history = []
    switched_history = []

    def on_switch(new_model):
        switched_history.append(new_model)

    def mock_call(model_name):
        call_history.append(model_name)
        if len(call_history) == 1:
            # Attempt 1: M1 fails with 503
            raise RuntimeError("503 UNAVAILABLE (high demand)")
        elif len(call_history) == 2:
            # Attempt 2: M2 fails with 504
            raise RuntimeError("504 DEADLINE_EXCEEDED")
        elif len(call_history) == 3:
            # Attempt 3: M1 succeeds
            return "m1_succeeded_on_attempt_3"
        return "unexpected"

    result = service._execute_with_failover(
        mock_call,
        op_id="TEST-PING-PONG",
        on_model_switch=on_switch,
    )

    assert result == "m1_succeeded_on_attempt_3"
    assert call_history == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    assert switched_history == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    assert service.active_model_id == "gemini-3.1-flash-lite"
    assert service.is_fallback_active is False


def test_alternating_exhaustion_sequence():
    """Verify all 4 attempts alternate [M1, M2, M1, M2] before giving up."""
    service = GeminiService(api_key="mock_key", model_id="gemini-3.1-flash-lite", fallback_model_id="gemini-3.5-flash-lite")
    call_history = []

    def mock_call(model_name):
        call_history.append(model_name)
        raise RuntimeError("503 UNAVAILABLE: Model overloaded")

    with pytest.raises(RuntimeError, match="failed across 4 attempts"):
        service._execute_with_failover(mock_call, op_id="TEST-EXHAUSTION")

    assert call_history == [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
    ]

