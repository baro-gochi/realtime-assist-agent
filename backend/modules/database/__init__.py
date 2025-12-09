"""데이터베이스 모듈.

PostgreSQL 및 Redis 연동을 위한 비동기 데이터베이스 모듈입니다.
asyncpg와 redis-py를 사용하여 고성능 비동기 DB 작업을 지원합니다.

주요 기능:
    - PostgreSQL Connection Pool 관리
    - Redis 연결 관리
    - 룸/참가자/대화 내용 저장
    - 시스템 로그 DB 저장
    - KT 멤버십 FAQ 캐싱 및 검색
"""

from .connection import DatabaseManager, get_db_manager
from .redis_connection import RedisManager, get_redis_manager
from .repository import (
    RoomRepository,
    TranscriptRepository,
    SystemLogRepository,
)
from .log_handler import DatabaseLogHandler
from .faq_service import FAQService, get_faq_service

__all__ = [
    "DatabaseManager",
    "get_db_manager",
    "RedisManager",
    "get_redis_manager",
    "RoomRepository",
    "TranscriptRepository",
    "SystemLogRepository",
    "DatabaseLogHandler",
    "FAQService",
    "get_faq_service",
]
