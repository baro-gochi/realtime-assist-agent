"""데이터베이스 연결 관리 모듈.

asyncpg를 사용한 PostgreSQL 연결 풀 관리를 담당합니다.

Examples:
    >>> from modules.database import get_db_manager
    >>> db = get_db_manager()
    >>> await db.initialize()
    >>> async with db.acquire() as conn:
    ...     result = await conn.fetch("SELECT * FROM rooms")
    >>> await db.close()
"""

import os
import json
import logging
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseManager:
    """PostgreSQL 연결 풀을 관리하는 싱글톤 클래스.

    Attributes:
        pool: asyncpg 연결 풀
        _initialized: 초기화 완료 여부
    """

    _instance: Optional["DatabaseManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.pool = None
            cls._instance._initialized = False
        return cls._instance

    @property
    def database_url(self) -> str:
        """환경변수에서 DATABASE_URL을 가져옵니다."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://assistant:assistant123@localhost:5432/realtime_assist"
        )

    @property
    def is_initialized(self) -> bool:
        """DB 연결 초기화 완료 여부."""
        return self._initialized and self.pool is not None

    async def _init_connection(self, conn: asyncpg.Connection):
        """각 연결에 JSONB 코덱을 설정합니다."""
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )

    async def initialize(self, min_size: int = 5, max_size: int = 20) -> bool:
        """연결 풀을 초기화합니다.

        Args:
            min_size: 최소 연결 수 (기본값: 5)
            max_size: 최대 연결 수 (기본값: 20)

        Returns:
            bool: 초기화 성공 여부
        """
        if self._initialized:
            logger.info("[DB] 이미 초기화됨")
            return True

        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
                init=self._init_connection,
            )
            self._initialized = True
            logger.info(f"[DB] 연결 풀 초기화 완료 (min={min_size}, max={max_size})")
            return True
        except Exception as e:
            logger.error(f"[DB] 초기화 실패: {e}")
            self._initialized = False
            return False

    async def close(self):
        """연결 풀을 종료합니다."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self._initialized = False
            logger.info("[DB] 연결 풀 종료")

    @asynccontextmanager
    async def acquire(self):
        """연결 풀에서 연결을 획득합니다.

        Yields:
            asyncpg.Connection: 데이터베이스 연결

        Raises:
            RuntimeError: DB가 초기화되지 않은 경우

        Examples:
            >>> async with db.acquire() as conn:
            ...     await conn.execute("INSERT INTO ...")
        """
        if not self.is_initialized:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """단일 쿼리를 실행합니다.

        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터

        Returns:
            str: 실행 결과 상태
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """여러 행을 조회합니다.

        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터

        Returns:
            list: 조회 결과 레코드 리스트
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """단일 행을 조회합니다.

        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터

        Returns:
            Optional[asyncpg.Record]: 조회 결과 레코드 또는 None
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """단일 값을 조회합니다.

        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터

        Returns:
            조회된 값 또는 None
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)


# 싱글톤 인스턴스 getter
def get_db_manager() -> DatabaseManager:
    """DatabaseManager 싱글톤 인스턴스를 반환합니다."""
    return DatabaseManager()
