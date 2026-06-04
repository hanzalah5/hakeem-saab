"""Integration tests for femverse.tools.user_data against real Cassandra.

The three tools are ``async def``; tests are decorated with
``@pytest.mark.asyncio`` and ``await`` the calls. Test-setup/teardown still
uses the sync ``client.run_query`` because that path is plain infrastructure,
not the ADK tool path under test.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from femverse.cassandra.cassandra_client import get_cassandra_session
from femverse.tools.user_data import (
    fetch_period_daily_logs,
    fetch_pregnancy_daily_logs,
    fetch_user_persona,
)

TEST_USER_ID_STRING = "test_user_001"
TEST_USER_ID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestCassandraIntegration:
    """Integration tests with real Cassandra connection."""

    @classmethod
    def setup_class(cls):
        cls.client = get_cassandra_session()
        cls._ensure_keyspace()
        cls._ensure_tables()
        cls._cleanup_test_data()

    @classmethod
    def teardown_class(cls):
        cls._cleanup_test_data()

    @classmethod
    def _ensure_keyspace(cls):
        try:
            cls.client.run_query(
                """
                CREATE KEYSPACE IF NOT EXISTS womensuperhealth
                WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}
                """
            )
        except Exception as e:
            print(f"Keyspace creation (may already exist): {e}")

    @classmethod
    def _ensure_tables(cls):
        # Tables are pre-created in the Cassandra instance.
        pass

    @classmethod
    def _cleanup_test_data(cls):
        try:
            test_uuid = uuid.UUID(TEST_USER_ID_UUID)
            cls.client.run_query(
                "DELETE FROM user_personas WHERE user_id = %s",
                (test_uuid,),
            )
            cls.client.run_query(
                "DELETE FROM period_llm_response_history WHERE user_id = %s",
                (test_uuid,),
            )
            cls.client.run_query(
                "DELETE FROM pregnancy_llm_response_history WHERE user_id = %s",
                (test_uuid,),
            )
        except Exception:
            # Expected if no data exists.
            pass

    @pytest.mark.asyncio
    async def test_fetch_user_persona_from_cassandra(self):
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)

        persona_data = {
            "age": 32,
            "weight_kg": 68,
            "height_cm": 168,
            "known_conditions": ["PCOS", "hypothyroidism"],
            "preferences": {"language": "en", "tone": "professional"},
        }

        self.client.run_query(
            """
            INSERT INTO user_personas
            (user_id, persona_type, persona_data, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_uuid, "health_profile", json.dumps(persona_data), now),
        )

        result = await fetch_user_persona(TEST_USER_ID_UUID)

        assert result is not None
        assert result["age"] == 32
        assert result["weight_kg"] == 68
        assert result["known_conditions"] == ["PCOS", "hypothyroidism"]

    @pytest.mark.asyncio
    async def test_fetch_user_persona_nonexistent(self):
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"
        result = await fetch_user_persona(nonexistent_uuid)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_period_daily_logs(self):
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")

        log_data = {
            "cycle_day": 14,
            "phase": "ovulatory",
            "flow_intensity": "none",
            "symptoms": ["mild_cramping", "mood_stable"],
            "temperature": 36.9,
        }

        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now, json.dumps(log_data)),
        )

        result = await fetch_period_daily_logs(TEST_USER_ID_UUID)

        assert result is not None
        assert len(result) >= 1
        assert result[0]["cycle_day"] == 14
        assert result[0]["phase"] == "ovulatory"
        assert "symptoms" in result[0]

    @pytest.mark.asyncio
    async def test_fetch_pregnancy_daily_logs(self):
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")

        log_data = {
            "gestational_age_weeks": 24,
            "gestational_age_days": 3,
            "fetal_movements": 45,
            "bp_systolic": 118,
            "bp_diastolic": 76,
            "glucose_fasting": 92,
        }

        self.client.run_query(
            """
            INSERT INTO pregnancy_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now, json.dumps(log_data)),
        )

        result = await fetch_pregnancy_daily_logs(TEST_USER_ID_UUID)

        assert result is not None
        assert len(result) >= 1
        assert result[0]["gestational_age_weeks"] == 24
        assert result[0]["fetal_movements"] == 45

    @pytest.mark.asyncio
    async def test_period_and_pregnancy_logs_are_independent(self):
        """The two tools target their own tables; neither falls back to the other."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")

        self.client.run_query(
            "DELETE FROM period_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )
        self.client.run_query(
            "DELETE FROM pregnancy_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )

        pregnancy_data = {"gestational_age_weeks": 20}
        self.client.run_query(
            """
            INSERT INTO pregnancy_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now, json.dumps(pregnancy_data)),
        )

        # Period tool sees its own (empty) table only -- no fallback.
        period_result = await fetch_period_daily_logs(TEST_USER_ID_UUID)
        assert period_result is None

        # Pregnancy tool returns its own row.
        pregnancy_result = await fetch_pregnancy_daily_logs(TEST_USER_ID_UUID)
        assert pregnancy_result is not None
        assert pregnancy_result[0]["gestational_age_weeks"] == 20

    @pytest.mark.asyncio
    async def test_fetch_period_logs_no_data(self):
        empty_uuid = "99999999-9999-9999-9999-999999999999"
        assert await fetch_period_daily_logs(empty_uuid) is None

    @pytest.mark.asyncio
    async def test_fetch_pregnancy_logs_no_data(self):
        empty_uuid = "99999999-9999-9999-9999-999999999999"
        assert await fetch_pregnancy_daily_logs(empty_uuid) is None

    @pytest.mark.asyncio
    async def test_fetch_period_logs_old_date_excluded(self):
        """Logs from yesterday are not returned by today's bounded query."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        yesterday_year_month = yesterday.strftime("%Y_%m")

        log_data = {"cycle_day": 5, "phase": "menstrual"}
        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, yesterday_year_month, 1, yesterday, json.dumps(log_data)),
        )

        result = await fetch_period_daily_logs(TEST_USER_ID_UUID)

        # Either nothing for today, or a different row that isn't yesterday's.
        if result is not None:
            assert not (len(result) == 1 and result[0] == log_data)

    @pytest.mark.asyncio
    async def test_fetch_user_persona_with_string_id(self):
        """String UUID inputs are normalized to UUID objects internally."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)

        persona_data = {"age": 28, "test_case": "string_normalization"}
        self.client.run_query(
            """
            INSERT INTO user_personas
            (user_id, persona_type, persona_data, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_uuid, "health_profile", json.dumps(persona_data), now),
        )

        result = await fetch_user_persona(TEST_USER_ID_UUID)

        assert result is not None
        assert result["age"] == 28
        assert result["test_case"] == "string_normalization"

    @pytest.mark.asyncio
    async def test_fetch_period_logs_multiple_entries_today(self):
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")

        self.client.run_query(
            "DELETE FROM period_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )

        log_data_1 = {"cycle_day": 12, "phase": "ovulatory", "time": "morning"}
        log_data_2 = {"cycle_day": 12, "phase": "ovulatory", "time": "evening"}

        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now - timedelta(hours=2), json.dumps(log_data_1)),
        )
        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 2, now, json.dumps(log_data_2)),
        )

        result = await fetch_period_daily_logs(TEST_USER_ID_UUID)

        assert result is not None
        assert len(result) >= 1


@pytest.mark.integration
class TestCassandraConnectionSetup:
    """Test Cassandra connection setup."""

    def test_cassandra_client_accessible(self):
        client = get_cassandra_session()
        assert client is not None

    def test_cassandra_client_singleton(self):
        client1 = get_cassandra_session()
        client2 = get_cassandra_session()
        assert client1 is client2

    def test_cassandra_keyspace_configured(self):
        from femverse.config.settings import settings

        assert settings.cassandra_keyspace == "womensuperhealth"
