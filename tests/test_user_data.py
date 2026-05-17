"""Test suite for agent.tools.user_data functions."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest

from agent.tools.user_data import (
    fetch_user_persona,
    fetch_daily_logs,
    _decode_persona_payload,
    _normalize_user_id,
)


class TestNormalizeUserId:
    """Test _normalize_user_id helper."""

    def test_normalize_uuid_string(self):
        """UUID string should be converted to UUID object."""
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        result = _normalize_user_id(user_id)
        assert isinstance(result, uuid.UUID)
        assert str(result) == user_id

    def test_normalize_non_uuid_string(self):
        """Non-UUID string should be returned as-is."""
        user_id = "usr_12345"
        result = _normalize_user_id(user_id)
        assert result == user_id
        assert isinstance(result, str)

    def test_normalize_invalid_input(self):
        """Invalid input should be returned as-is."""
        user_id = "not-a-valid-uuid"
        result = _normalize_user_id(user_id)
        assert result == user_id


class TestDecodePersonaPayload:
    """Test _decode_persona_payload helper."""

    def test_decode_dict_payload(self):
        """Dict payload should be returned as-is."""
        payload = {"age": 30, "weight_kg": 65}
        result = _decode_persona_payload(payload)
        assert result == payload

    def test_decode_json_string_payload(self):
        """JSON string payload should be decoded to dict."""
        payload = '{"age": 30, "weight_kg": 65}'
        result = _decode_persona_payload(payload)
        assert result == {"age": 30, "weight_kg": 65}

    def test_decode_bytes_payload(self):
        """Bytes payload should be decoded to dict."""
        payload = b'{"age": 30, "weight_kg": 65}'
        result = _decode_persona_payload(payload)
        assert result == {"age": 30, "weight_kg": 65}

    def test_decode_none_payload(self):
        """None payload should return None."""
        result = _decode_persona_payload(None)
        assert result is None

    def test_decode_invalid_json_string(self):
        """Invalid JSON string should be wrapped in persona_data."""
        payload = "not valid json"
        result = _decode_persona_payload(payload)
        assert result == {"persona_data": "not valid json"}

    def test_decode_non_dict_json(self):
        """Non-dict JSON should be wrapped in persona_data."""
        payload = "[1, 2, 3]"
        result = _decode_persona_payload(payload)
        assert result == {"persona_data": [1, 2, 3]}


class MockRow:
    """Mock Cassandra row object."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestFetchUserPersona:
    """Test fetch_user_persona function."""

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_persona_success_dict(self, mock_get_session):
        """Should return persona dict when query succeeds."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        persona_data = {"age": 30, "weight_kg": 65, "known_conditions": ["PCOS"]}
        mock_row = MockRow(persona_data=persona_data)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_user_persona("usr_12345")
        
        assert result == persona_data
        mock_client.run_query.assert_called_once()

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_persona_success_json_string(self, mock_get_session):
        """Should decode and return persona from JSON string."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        persona_data = '{"age": 28, "weight_kg": 62}'
        mock_row = MockRow(persona_data=persona_data)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_user_persona("usr_12345")
        
        assert result == {"age": 28, "weight_kg": 62}

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_persona_no_rows(self, mock_get_session):
        """Should return None when no rows found."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        mock_client.run_query.return_value = []
        
        result = fetch_user_persona("nonexistent_user")
        
        assert result is None

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_persona_cassandra_exception(self, mock_get_session):
        """Should return None on Cassandra exception."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        mock_client.run_query.side_effect = Exception("Connection timeout")
        
        result = fetch_user_persona("usr_12345")
        
        assert result is None

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_persona_with_uuid(self, mock_get_session):
        """Should normalize UUID user_id."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        persona_data = {"age": 25}
        mock_row = MockRow(persona_data=persona_data)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_user_persona(user_uuid)
        
        assert result == persona_data
        # Verify UUID was normalized
        call_args = mock_client.run_query.call_args[0]
        assert isinstance(call_args[1][0], uuid.UUID)


class TestFetchDailyLogs:
    """Test fetch_daily_logs function."""

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_period_success(self, mock_get_session):
        """Should return logs from period_llm_response_history when available."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        log_data = {
            "cycle_day": 15,
            "phase": "follicular",
            "flow_intensity": "moderate",
        }
        mock_row = MockRow(user_data=log_data)
        
        # First call (period) returns data
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result == [log_data]
        # Should only call once (period table)
        assert mock_client.run_query.call_count == 1

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_period_empty_pregnancy_success(self, mock_get_session):
        """Should fallback to pregnancy_llm_response_history when period is empty."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        pregnancy_data = {"gestational_age": 18, "fetal_movements": 25}
        mock_row = MockRow(user_data=pregnancy_data)
        
        # First call (period) returns empty, second call (pregnancy) returns data
        mock_client.run_query.side_effect = [[], [mock_row]]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result == [pregnancy_data]
        # Should call twice (period, then pregnancy)
        assert mock_client.run_query.call_count == 2

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_both_empty(self, mock_get_session):
        """Should return None when both period and pregnancy tables are empty."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        # Both calls return empty
        mock_client.run_query.side_effect = [[], []]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result is None
        assert mock_client.run_query.call_count == 2

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_period_exception_pregnancy_success(self, mock_get_session):
        """Should fallback to pregnancy when period query raises exception."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        pregnancy_data = {"gestational_age": 20}
        mock_row = MockRow(user_data=pregnancy_data)
        
        # First call raises, second call succeeds
        mock_client.run_query.side_effect = [
            Exception("Period table not found"),
            [mock_row],
        ]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result == [pregnancy_data]

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_both_exceptions(self, mock_get_session):
        """Should return None when both queries raise exceptions."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        mock_client.run_query.side_effect = [
            Exception("Period error"),
            Exception("Pregnancy error"),
        ]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result is None

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_json_string_payload(self, mock_get_session):
        """Should decode JSON string payload from Cassandra."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        log_json = '{"cycle_day": 12, "symptoms": ["cramps", "headache"]}'
        mock_row = MockRow(user_data=log_json)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result == [{"cycle_day": 12, "symptoms": ["cramps", "headache"]}]

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_with_uuid(self, mock_get_session):
        """Should normalize UUID user_id."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        log_data = {"cycle_day": 10}
        mock_row = MockRow(user_data=log_data)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_daily_logs(user_uuid)
        
        assert result == [log_data]
        # Verify UUID was normalized
        call_args = mock_client.run_query.call_args[0]
        assert isinstance(call_args[1][0], uuid.UUID)

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_time_bounds(self, mock_get_session):
        """Should query with correct date/time bounds."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        mock_client.run_query.side_effect = [[], []]
        
        # Just verify the query is called with date bounds
        fetch_daily_logs("usr_12345")
        
        # Check that time bounds were passed correctly
        calls = mock_client.run_query.call_args_list
        assert len(calls) == 2  # Period and pregnancy queries
        
        for call in calls:
            query_args = call[0][1]
            # args[0] = user_id, args[1] = year_month, args[2] = day_start, args[3] = day_end
            year_month = query_args[1]
            day_start = query_args[2]
            day_end = query_args[3]
            
            # Verify year_month format (YYYY_MM)
            assert len(year_month) == 7  # e.g., "2026_05"
            assert year_month[4] == "_"
            
            # Verify time bounds are datetime objects
            assert isinstance(day_start, datetime)
            assert isinstance(day_end, datetime)
            assert day_start < day_end

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_none_payload(self, mock_get_session):
        """Should return None when payload is None."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        mock_row = MockRow(user_data=None)
        mock_client.run_query.side_effect = [[mock_row], []]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result is None

    @patch("agent.tools.user_data.get_cassandra_session")
    def test_fetch_daily_logs_bytes_payload(self, mock_get_session):
        """Should decode bytes payload."""
        mock_client = MagicMock()
        mock_get_session.return_value = mock_client
        
        log_json_bytes = b'{"cycle_day": 8, "flow": "light"}'
        mock_row = MockRow(user_data=log_json_bytes)
        mock_client.run_query.return_value = [mock_row]
        
        result = fetch_daily_logs("usr_12345")
        
        assert result == [{"cycle_day": 8, "flow": "light"}]
