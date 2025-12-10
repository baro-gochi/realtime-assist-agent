"""Backend modules package.

이 패키지는 WebRTC 기반 실시간 상담 시스템의 핵심 모듈을 포함합니다.

Modules:
    webrtc: WebRTC 피어 연결 및 룸 관리
    stt: Google Cloud Speech-to-Text 음성 인식
    agent: LangGraph 기반 대화 요약 에이전트
    database: PostgreSQL 데이터베이스 연동
    vector_db: ChromaDB 벡터 데이터베이스 관리
    consultation: RAG 기반 상담 지원 에이전트

NOTE: 순환 import 방지를 위해 무거운 모듈은 lazy import합니다.
      직접 import 권장:
      - from modules.vector_db.manager import get_vector_db_manager
      - from modules.consultation.workflow import run_consultation_async
"""

# 가벼운 모듈만 즉시 import
from .webrtc import PeerConnectionManager, RoomManager, AudioRelayTrack
from .stt import STTService, STTAdaptationConfig
from .agent import create_agent_graph, get_or_create_agent, remove_agent, RoomAgent
from .database import (
    DatabaseManager,
    get_db_manager,
    RedisManager,
    get_redis_manager,
    RoomRepository,
    TranscriptRepository,
    SystemLogRepository,
    DatabaseLogHandler,
)

# 무거운 모듈은 lazy import (순환 import 방지)
def __getattr__(name):
    """Lazy import for heavy modules to avoid circular imports."""

    # Vector DB
    if name in (
        "VectorDBManager", "get_vector_db_manager", "reset_vector_db_manager",
        "DocumentRegistry", "get_doc_registry", "reset_doc_registry",
    ):
        from . import vector_db
        if name in ("VectorDBManager", "get_vector_db_manager", "reset_vector_db_manager"):
            from .vector_db.manager import VectorDBManager, get_vector_db_manager, reset_vector_db_manager
            return locals()[name]
        else:
            from .vector_db.doc_registry import DocumentRegistry, get_doc_registry, reset_doc_registry
            return locals()[name]

    # Consultation
    if name in (
        "run_consultation", "run_consultation_async",
        "consultation_router", "comparison_router", "faq_router",
        "consultation_settings", "request_limiter", "get_queue_status",
    ):
        from . import consultation
        return getattr(consultation, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # WebRTC
    "PeerConnectionManager",
    "RoomManager",
    "AudioRelayTrack",
    # STT
    "STTService",
    "STTAdaptationConfig",
    # Agent (real-time summarization)
    "create_agent_graph",
    "get_or_create_agent",
    "remove_agent",
    "RoomAgent",
    # Database
    "DatabaseManager",
    "get_db_manager",
    "RedisManager",
    "get_redis_manager",
    "RoomRepository",
    "TranscriptRepository",
    "SystemLogRepository",
    "DatabaseLogHandler",
    # Vector DB
    "VectorDBManager",
    "get_vector_db_manager",
    "reset_vector_db_manager",
    "DocumentRegistry",
    "get_doc_registry",
    "reset_doc_registry",
    # Consultation
    "run_consultation",
    "run_consultation_async",
    "consultation_router",
    "comparison_router",
    "faq_router",
    "consultation_settings",
    "request_limiter",
    "get_queue_status",
]
