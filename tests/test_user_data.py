"""Test suite for femverse.tools.user_data functions.

The three tools fetch from Cassandra via ``CassandraClient.run_query_async``;
they are ``async def`` so the asyncio loop is not blocked under concurrent
ADK runs. Tests mock the async client method with ``AsyncMock`` and use
``@pytest.mark.asyncio`` to drive them.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from femverse.tools.user_data import (
    _decode_persona_payload,
    _normalize_user_id,
    fetch_period_daily_logs,
    fetch_pregnancy_daily_logs,
    fetch_user_persona,
)


class TestNormalizeUserId:
    """Test _normalize_user_id helper."""

    def test_normalize_uuid_string(self):
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        result = _normalize_user_id(user_id)
        assert isinstance(result, uuid.UUID)
        assert str(result) == user_id

    def test_normalize_non_uuid_string(self):
        user_id = "usr_12345"
        result = _normalize_user_id(user_id)
        assert result == user_id
        assert isinstance(result, str)

    def test_normalize_invalid_input(self):
        user_id = "not-a-valid-uuid"
        result = _normalize_user_id(user_id)
        assert result == user_id


class TestDecodePersonaPayload:
    """Test _decode_persona_payload helper."""

    def test_decode_dict_payload(self):
        payload = {"age": 30, "weight_kg": 65}
        assert _decode_persona_payload(payload) == payload

    def test_decode_json_string_payload(self):
        payload = '{"age": 30, "weight_kg": 65}'
        assert _decode_persona_payload(payload) == {"age": 30, "weight_kg": 65}

    def test_decode_bytes_payload(self):
        payload = b'{"age": 30, "weight_kg": 65}'
        assert _decode_persona_payload(payload) == {"age": 30, "weight_kg": 65}

    def test_decode_none_payload(self):
        assert _decode_persona_payload(None) is None

    def test_decode_invalid_json_string(self):
        assert _decode_persona_payload("not valid json") == {
            "persona_data": "not valid json"
        }

    def test_decode_non_dict_json(self):
        assert _decode_persona_payload("[1, 2, 3]") == {"persona_data": [1, 2, 3]}


class MockRow:
    """Mock Cassandra row object."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _make_client(return_value=None, side_effect=None):
    """Build a mock CassandraClient whose ``run_query_async`` is awaitable."""
    client = MagicMock()
    client.run_query_async = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


class TestFetchUserPersona:
    """Test fetch_user_persona function."""

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_persona_success_dict(self, mock_get_session):
        persona_data = {"age": 30, "weight_kg": 65, "known_conditions": ["PCOS"]}
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(persona_data=persona_data)]
        )

        result = await fetch_user_persona("usr_12345")

        assert result == persona_data
        mock_get_session.return_value.run_query_async.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_persona_success_json_string(self, mock_get_session):
        persona_json = '{"age": 28, "weight_kg": 62}'
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(persona_data=persona_json)]
        )

        result = await fetch_user_persona("usr_12345")

        assert result == {"age": 28, "weight_kg": 62}

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_persona_no_rows(self, mock_get_session):
        mock_get_session.return_value = _make_client(return_value=[])

        result = await fetch_user_persona("nonexistent_user")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_persona_cassandra_exception(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            side_effect=Exception("Connection timeout")
        )

        result = await fetch_user_persona("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_persona_with_uuid(self, mock_get_session):
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(persona_data={"age": 25})]
        )

        result = await fetch_user_persona(user_uuid)

        assert result == {"age": 25}
        call_args = mock_get_session.return_value.run_query_async.await_args[0]
        assert isinstance(call_args[1][0], uuid.UUID)


class TestFetchPeriodDailyLogs:
    """Test fetch_period_daily_logs function."""

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_success(self, mock_get_session):
        log_data = {
            "cycle_day": 15,
            "phase": "follicular",
            "flow_intensity": "moderate",
        }
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=log_data)]
        )

        result = await fetch_period_daily_logs("usr_12345")

        assert result == [log_data]
        assert mock_get_session.return_value.run_query_async.await_count == 1

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_no_rows(self, mock_get_session):
        mock_get_session.return_value = _make_client(return_value=[])

        result = await fetch_period_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_exception(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            side_effect=Exception("Period table unavailable")
        )

        result = await fetch_period_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_json_string_payload(self, mock_get_session):
        payload = '{"cycle_day": 12, "symptoms": ["cramps", "headache"]}'
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=payload)]
        )

        result = await fetch_period_daily_logs("usr_12345")

        assert result == [{"cycle_day": 12, "symptoms": ["cramps", "headache"]}]

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_bytes_payload(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=b'{"cycle_day": 8, "flow": "light"}')]
        )

        result = await fetch_period_daily_logs("usr_12345")

        assert result == [{"cycle_day": 8, "flow": "light"}]

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_none_payload(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=None)]
        )

        result = await fetch_period_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_with_uuid(self, mock_get_session):
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data={"cycle_day": 10})]
        )

        result = await fetch_period_daily_logs(user_uuid)

        assert result == [{"cycle_day": 10}]
        call_args = mock_get_session.return_value.run_query_async.await_args[0]
        assert isinstance(call_args[1][0], uuid.UUID)

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_period_logs_time_bounds(self, mock_get_session):
        mock_get_session.return_value = _make_client(return_value=[])

        await fetch_period_daily_logs("usr_12345")

        query_args = mock_get_session.return_value.run_query_async.await_args[0][1]
        # (user_id, year_month, day_start, day_end)
        year_month = query_args[1]
        day_start = query_args[2]
        day_end = query_args[3]

        assert len(year_month) == 7
        assert year_month[4] == "_"
        assert isinstance(day_start, datetime)
        assert isinstance(day_end, datetime)
        assert day_start < day_end


class TestFetchPregnancyDailyLogs:
    """Test fetch_pregnancy_daily_logs function."""

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_success(self, mock_get_session):
        log_data = {
            "gestational_age_weeks": 22,
            "fetal_movements": 30,
            "bp_systolic": 120,
        }
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=log_data)]
        )

        result = await fetch_pregnancy_daily_logs("usr_12345")

        assert result == [log_data]
        assert mock_get_session.return_value.run_query_async.await_count == 1

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_no_rows(self, mock_get_session):
        mock_get_session.return_value = _make_client(return_value=[])

        result = await fetch_pregnancy_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_exception(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            side_effect=Exception("Pregnancy table unavailable")
        )

        result = await fetch_pregnancy_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_json_string_payload(self, mock_get_session):
        payload = '{"gestational_age_weeks": 30, "notes": "feeling great"}'
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=payload)]
        )

        result = await fetch_pregnancy_daily_logs("usr_12345")

        assert result == [{"gestational_age_weeks": 30, "notes": "feeling great"}]

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_none_payload(self, mock_get_session):
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data=None)]
        )

        result = await fetch_pregnancy_daily_logs("usr_12345")

        assert result is None

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_with_uuid(self, mock_get_session):
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        mock_get_session.return_value = _make_client(
            return_value=[MockRow(user_data={"gestational_age_weeks": 18})]
        )

        result = await fetch_pregnancy_daily_logs(user_uuid)

        assert result == [{"gestational_age_weeks": 18}]
        call_args = mock_get_session.return_value.run_query_async.await_args[0]
        assert isinstance(call_args[1][0], uuid.UUID)

    @pytest.mark.asyncio
    @patch("femverse.tools.user_data.get_cassandra_session")
    async def test_fetch_pregnancy_logs_time_bounds(self, mock_get_session):
        mock_get_session.return_value = _make_client(return_value=[])

        await fetch_pregnancy_daily_logs("usr_12345")

        query_args = mock_get_session.return_value.run_query_async.await_args[0][1]
        year_month = query_args[1]
        day_start = query_args[2]
        day_end = query_args[3]

        assert len(year_month) == 7
        assert year_month[4] == "_"
        assert isinstance(day_start, datetime)
        assert isinstance(day_end, datetime)
        assert day_start < day_end
