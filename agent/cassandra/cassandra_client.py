import asyncio
from functools import lru_cache
from typing import Optional, Any

from cassandra.cluster import Cluster, Session, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement
from concurrent.futures import ThreadPoolExecutor

import logging

from agent.config.settings import settings

logger = logging.getLogger()


class CassandraClient:
    def __init__(
        self,
        contact_points: list[str] | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        keyspace: str | None = None,
        max_workers: int = 5,
    ):
        self.contact_points = contact_points or [settings.cassandra_host]
        self.port = port or settings.cassandra_port
        self.username = username or settings.cassandra_username
        self.password = password or settings.cassandra_password
        self.keyspace = keyspace or settings.cassandra_keyspace
        self.cluster = None
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=max_workers)


    def connect(self):
        logger.info("Connecting to Cassandra...")

        auth_provider = PlainTextAuthProvider(username=self.username, password=self.password)
        self.cluster = Cluster(
            contact_points=self.contact_points,
            port=self.port,
            auth_provider=auth_provider,
            protocol_version=5,
            execution_profiles={
                EXEC_PROFILE_DEFAULT: ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="dc1"))
            }
        )
        self.session = self.cluster.connect()
        self._ensure_keyspace_exists()
        self.session.set_keyspace(self.keyspace)

        logger.info("Connected to Cassandra.")


    def close(self):
        if self.cluster:
            logger.info("Closing Cassandra cluster connection.")
            self.cluster.shutdown()
            self.cluster = None
            self.session = None


    def _ensure_keyspace_exists(self):
        logger.info(f"Checking if keyspace '{self.keyspace}' exists...")

        query = f"""
        CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
        WITH replication = {{
            'class': 'SimpleStrategy',
            'replication_factor': '1'
        }}
        """

        self.session.execute(SimpleStatement(query))

        logger.info(f"Keyspace '{self.keyspace}' is ready.")


    def get_session(self) -> Session:
        if self.session is None:
            self.connect()

        return self.session


    def run_query(self, query: str, parameters: Optional[tuple] = None) -> Any:
        session = self.get_session()

        if parameters:
            return session.execute(query, parameters)

        return session.execute(query)


    async def run_query_async(self, query: str, parameters: Optional[tuple] = None) -> Any:
        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(
            self.executor,
            lambda: self.run_query(query, parameters),
        )


@lru_cache(maxsize=1)
def get_cassandra_session() -> CassandraClient:
    return CassandraClient()
