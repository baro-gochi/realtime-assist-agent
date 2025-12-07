"""Redis 연결 관리 모듈.

redis-py를 사용한 Redis 연결 관리를 담당합니다.

Examples:
    >>> from modules.database import get_redis_manager
    >>> redis_mgr = get_redis_manager()
    >>> await redis_mgr.initialize()
    >>> await redis_mgr.ping()
    >>> await redis_mgr.close()
"""

import os
import logging
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis 연결을 관리하는 싱글톤 클래스.

    Attributes:
        client: redis 클라이언트
        _initialized: 초기화 완료 여부
    """

    _instance: Optional["RedisManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = None
            cls._instance._initialized = False
        return cls._instance

    @property
    def redis_url(self) -> str:
        """환경변수에서 REDIS_URL을 가져옵니다."""
        return os.getenv("REDIS_URL", "redis://localhost:6379")

    @property
    def is_initialized(self) -> bool:
        """Redis 연결 초기화 완료 여부."""
        return self._initialized and self.client is not None

    async def initialize(self) -> bool:
        """Redis 연결을 초기화합니다.

        Returns:
            bool: 초기화 성공 여부
        """
        if self._initialized:
            logger.info("Redis already initialized")
            return True

        try:
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self.client.ping()
            self._initialized = True
            logger.info(f"Redis connection initialized: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            self._initialized = False
            return False

    async def close(self):
        """Redis 연결을 종료합니다."""
        if self.client:
            await self.client.close()
            self.client = None
            self._initialized = False
            logger.info("Redis connection closed")

    async def ping(self) -> bool:
        """Redis 서버에 ping을 보냅니다.

        Returns:
            bool: ping 성공 여부
        """
        if not self.is_initialized:
            return False
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def get(self, key: str) -> Optional[str]:
        """키에 해당하는 값을 조회합니다."""
        if not self.is_initialized:
            raise RuntimeError("Redis not initialized. Call initialize() first.")
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """키-값을 저장합니다.

        Args:
            key: 키
            value: 값
            ex: 만료 시간 (초)

        Returns:
            bool: 저장 성공 여부
        """
        if not self.is_initialized:
            raise RuntimeError("Redis not initialized. Call initialize() first.")
        return await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> int:
        """키를 삭제합니다."""
        if not self.is_initialized:
            raise RuntimeError("Redis not initialized. Call initialize() first.")
        return await self.client.delete(key)


# 싱글톤 인스턴스 getter
def get_redis_manager() -> RedisManager:
    """RedisManager 싱글톤 인스턴스를 반환합니다."""
    return RedisManager()
