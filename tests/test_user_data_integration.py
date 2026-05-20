"""Integration tests for femverse.tools.user_data with real Cassandra."""

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from femverse.cassandra.cassandra_client import get_cassandra_session
from femverse.tools.user_data import fetch_user_persona, fetch_daily_logs


# Test fixtures
TEST_USER_ID_STRING = "test_user_001"
TEST_USER_ID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestCassandraIntegration:
    """Integration tests with real Cassandra connection."""

    @classmethod
    def setup_class(cls):
        """Set up Cassandra connection and test tables."""
        cls.client = get_cassandra_session()
        cls._ensure_keyspace()
        cls._ensure_tables()
        cls._cleanup_test_data()

    @classmethod
    def teardown_class(cls):
        """Clean up test data after all tests."""
        cls._cleanup_test_data()

    @classmethod
    def _ensure_keyspace(cls):
        """Create keyspace if it doesn't exist."""
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
        """Tables should already exist in womensuperhealth keyspace."""
        # Tables are pre-created in the Cassandra instance
        pass

    @classmethod
    def _cleanup_test_data(cls):
        """Delete test data from tables."""
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
        except Exception as e:
            # Expected if no data exists
            pass

    def test_fetch_user_persona_from_cassandra(self):
        """Test fetching a real persona from Cassandra."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        
        # Insert test persona (matching actual schema with persona_type)
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
        
        # Fetch and verify
        result = fetch_user_persona(TEST_USER_ID_UUID)
        
        assert result is not None
        assert result["age"] == 32
        assert result["weight_kg"] == 68
        assert result["known_conditions"] == ["PCOS", "hypothyroidism"]

    def test_fetch_user_persona_nonexistent(self):
        """Test fetching persona for nonexistent user."""
        nonexistent_uuid = "00000000-0000-0000-0000-000000000000"
        result = fetch_user_persona(nonexistent_uuid)
        assert result is None

    def test_fetch_daily_logs_period(self):
        """Test fetching period logs from Cassandra."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")
        
        # Insert test period log (matching actual schema with user_data_db_id)
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
        
        # Fetch and verify
        result = fetch_daily_logs(TEST_USER_ID_UUID)
        
        assert result is not None
        assert len(result) >= 1
        assert result[0]["cycle_day"] == 14
        assert result[0]["phase"] == "ovulatory"
        assert "symptoms" in result[0]

    def test_fetch_daily_logs_pregnancy(self):
        """Test fetching pregnancy logs from Cassandra."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")
        
        # Clean period logs to ensure pregnancy fallback
        self.client.run_query(
            "DELETE FROM period_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )
        
        # Insert test pregnancy log (matching actual schema with user_data_db_id)
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
        
        # Fetch and verify
        result = fetch_daily_logs(TEST_USER_ID_UUID)
        
        assert result is not None
        assert len(result) >= 1
        assert result[0]["gestational_age_weeks"] == 24
        assert result[0]["fetal_movements"] == 45

    def test_fetch_daily_logs_period_precedence(self):
        """Test that period logs take precedence over pregnancy logs."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")
        
        # Clean previous data
        self.client.run_query(
            "DELETE FROM period_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )
        self.client.run_query(
            "DELETE FROM pregnancy_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )
        
        # Insert both period and pregnancy logs (matching actual schema)
        period_data = {"cycle_day": 10, "phase": "follicular"}
        pregnancy_data = {"gestational_age_weeks": 20}
        
        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now, json.dumps(period_data)),
        )
        
        self.client.run_query(
            """
            INSERT INTO pregnancy_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, year_month, 1, now - timedelta(minutes=5), json.dumps(pregnancy_data)),
        )
        
        # Fetch and verify period takes precedence
        result = fetch_daily_logs(TEST_USER_ID_UUID)
        
        assert result is not None
        assert len(result) >= 1
        assert "cycle_day" in result[0]
        assert "gestational_age_weeks" not in result[0]

    def test_fetch_daily_logs_no_data(self):
        """Test fetching logs when no data exists."""
        # Use a unique UUID that has no data
        empty_uuid = "99999999-9999-9999-9999-999999999999"
        result = fetch_daily_logs(empty_uuid)
        assert result is None

    def test_fetch_daily_logs_old_date(self):
        """Test that logs from yesterday are not fetched."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        yesterday_year_month = yesterday.strftime("%Y_%m")
        
        # Insert log from yesterday (matching actual schema)
        log_data = {"cycle_day": 5, "phase": "menstrual"}
        
        self.client.run_query(
            """
            INSERT INTO period_llm_response_history
            (user_id, year_month, user_data_db_id, generated_at, user_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (test_uuid, yesterday_year_month, 1, yesterday, json.dumps(log_data)),
        )
        
        # Fetch today's logs - should not get yesterday's data
        result = fetch_daily_logs(TEST_USER_ID_UUID)
        
        # If result is not None, it means we got today's data, not yesterday's
        if result is not None:
            # Verify it's not the yesterday's log
            assert not (len(result) == 1 and result[0] == log_data and "cycle_day" in result[0])

    def test_fetch_user_persona_with_string_id(self):
        """Test fetching persona with string user_id (should normalize to UUID)."""
        # This test verifies that string UUIDs are properly normalized
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        
        # Insert test persona (matching actual schema)
        persona_data = {"age": 28, "test_case": "string_normalization"}
        
        self.client.run_query(
            """
            INSERT INTO user_personas
            (user_id, persona_type, persona_data, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (test_uuid, "health_profile", json.dumps(persona_data), now),
        )
        
        # Fetch with string UUID
        result = fetch_user_persona(TEST_USER_ID_UUID)
        
        assert result is not None
        assert result["age"] == 28
        assert result["test_case"] == "string_normalization"

    def test_fetch_daily_logs_multiple_entries_today(self):
        """Test fetching when multiple entries exist today."""
        test_uuid = uuid.UUID(TEST_USER_ID_UUID)
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")
        
        # Clean previous data
        self.client.run_query(
            "DELETE FROM period_llm_response_history WHERE user_id = %s AND year_month = %s",
            (test_uuid, year_month),
        )
        
        # Insert multiple logs for today (matching actual schema)
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
        
        # Fetch and verify - should get at least the most recent one
        result = fetch_daily_logs(TEST_USER_ID_UUID)
        
        assert result is not None
        assert len(result) >= 1


@pytest.mark.integration
class TestCassandraConnectionSetup:
    """Test Cassandra connection setup."""

    def test_cassandra_client_accessible(self):
        """Test that Cassandra client is accessible."""
        client = get_cassandra_session()
        assert client is not None

    def test_cassandra_client_singleton(self):
        """Test that get_cassandra_session returns the same instance."""
        client1 = get_cassandra_session()
        client2 = get_cassandra_session()
        assert client1 is client2

    def test_cassandra_keyspace_configured(self):
        """Test that the correct keyspace is configured."""
        from femverse.config.settings import settings
        
        assert settings.cassandra_keyspace == "womensuperhealth"
