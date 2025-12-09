"""대기열 및 Rate Limiting 관리.

서버 안정성을 위한 요청 제어 기능을 제공합니다.

Usage:
    from modules.consultation.utils import request_limiter

    async with request_limiter.acquire():
        # 요청 처리
        pass
"""

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable
from functools import wraps

from modules.consultation.config import consultation_settings

logger = logging.getLogger(__name__)


@dataclass
class QueueStats:
    """대기열 통계 정보."""
    current_requests: int = 0
    max_requests: int = 10
    queue_length: int = 0
    total_processed: int = 0
    total_rejected: int = 0

    @property
    def is_accepting(self) -> bool:
        """새 요청 수락 가능 여부."""
        return self.current_requests < self.max_requests


class ConcurrencyLimiter:
    """동시 요청 수 제한기 (Semaphore 기반)."""

    def __init__(
        self,
        max_concurrent: int = None,
        timeout: float = None
    ):
        """ConcurrencyLimiter 초기화.

        Args:
            max_concurrent: 최대 동시 요청 수
            timeout: 대기 타임아웃 초
        """
        settings = consultation_settings
        self.max_concurrent = max_concurrent or settings.MAX_CONCURRENT_REQUESTS
        self.timeout = timeout or settings.REQUEST_TIMEOUT

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._current_count = 0
        self._waiting_count = 0
        self._total_processed = 0
        self._total_rejected = 0
        self._lock = asyncio.Lock()

        logger.info(f"ConcurrencyLimiter 초기화: max={self.max_concurrent}, timeout={self.timeout}s")

    @asynccontextmanager
    async def acquire(self, timeout: float = None):
        """요청 슬롯 획득 (컨텍스트 매니저).

        Args:
            timeout: 대기 타임아웃

        Raises:
            asyncio.TimeoutError: 타임아웃 시
        """
        timeout = timeout or self.timeout

        async with self._lock:
            self._waiting_count += 1

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=timeout
            )

            async with self._lock:
                self._waiting_count -= 1
                self._current_count += 1

            logger.debug(f"요청 슬롯 획득: {self._current_count}/{self.max_concurrent}")

            try:
                yield
            finally:
                self._semaphore.release()
                async with self._lock:
                    self._current_count -= 1
                    self._total_processed += 1
                logger.debug(f"요청 슬롯 반환: {self._current_count}/{self.max_concurrent}")

        except asyncio.TimeoutError:
            async with self._lock:
                self._waiting_count -= 1
                self._total_rejected += 1
            logger.warning(f"요청 타임아웃: 대기 시간 초과 ({timeout}s)")
            raise

    def get_stats(self) -> QueueStats:
        """현재 대기열 상태 조회."""
        return QueueStats(
            current_requests=self._current_count,
            max_requests=self.max_concurrent,
            queue_length=self._waiting_count,
            total_processed=self._total_processed,
            total_rejected=self._total_rejected
        )


class RateLimiter:
    """Rate Limiter (Token Bucket 알고리즘)."""

    def __init__(
        self,
        max_requests: int = None,
        window_seconds: int = 60
    ):
        """RateLimiter 초기화.

        Args:
            max_requests: 분당 최대 요청 수
            window_seconds: 시간 윈도우 크기 (초)
        """
        settings = consultation_settings
        self.max_requests = max_requests or settings.RATE_LIMIT_PER_MINUTE
        self.window_seconds = window_seconds

        self._request_times: deque = deque()
        self._lock = asyncio.Lock()

        logger.info(f"RateLimiter 초기화: {self.max_requests} req/{self.window_seconds}s")

    async def is_allowed(self) -> bool:
        """요청 허용 여부 확인."""
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self.window_seconds

            while self._request_times and self._request_times[0] < window_start:
                self._request_times.popleft()

            if len(self._request_times) < self.max_requests:
                self._request_times.append(current_time)
                return True
            else:
                logger.warning(f"Rate limit 초과: {len(self._request_times)}/{self.max_requests}")
                return False

    def get_remaining(self) -> int:
        """남은 요청 가능 횟수 조회."""
        current_time = time.time()
        window_start = current_time - self.window_seconds

        current_count = sum(
            1 for t in self._request_times if t >= window_start
        )

        return max(0, self.max_requests - current_count)


class RequestLimiter:
    """통합 요청 제한기.

    동시성 제한과 Rate Limiting을 모두 적용합니다.
    """

    def __init__(self):
        """RequestLimiter 초기화."""
        self.concurrency_limiter = ConcurrencyLimiter()
        self.rate_limiter = RateLimiter()
        logger.info("RequestLimiter 초기화 완료")

    @asynccontextmanager
    async def acquire(self, timeout: float = None):
        """요청 슬롯 획득 (Rate Limit + Concurrency 모두 적용).

        Raises:
            RuntimeError: Rate limit 초과 시
            asyncio.TimeoutError: 타임아웃 시
        """
        if not await self.rate_limiter.is_allowed():
            raise RuntimeError("Rate limit exceeded")

        async with self.concurrency_limiter.acquire(timeout=timeout):
            yield

    def limit(self, func: Callable):
        """요청 제한 데코레이터."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self.acquire():
                return await func(*args, **kwargs)
        return wrapper

    def get_stats(self) -> dict:
        """전체 상태 조회."""
        queue_stats = self.concurrency_limiter.get_stats()
        rate_remaining = self.rate_limiter.get_remaining()

        return {
            "concurrency": {
                "current": queue_stats.current_requests,
                "max": queue_stats.max_requests,
                "waiting": queue_stats.queue_length,
                "is_accepting": queue_stats.is_accepting
            },
            "rate_limit": {
                "remaining": rate_remaining,
                "max_per_minute": self.rate_limiter.max_requests
            },
            "totals": {
                "processed": queue_stats.total_processed,
                "rejected": queue_stats.total_rejected
            }
        }


# 싱글톤 인스턴스
request_limiter = RequestLimiter()


def get_queue_status() -> dict:
    """대기열 상태 조회 (편의 함수)."""
    return request_limiter.get_stats()
