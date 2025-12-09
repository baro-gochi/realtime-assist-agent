"""Backend modules package.

이 패키지는 WebRTC 기반 실시간 상담 시스템의 핵심 모듈을 포함합니다.

Modules:
    webrtc: WebRTC 피어 연결 및 룸 관리
    stt: Google Cloud Speech-to-Text 음성 인식
    agent: LangGraph 기반 대화 요약 에이전트
    database: PostgreSQL 데이터베이스 연동
    vector_db: ChromaDB 벡터 데이터베이스 관리
    consultation: RAG 기반 상담 지원 에이전트
"""

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
from .vector_db import (
    VectorDBManager,
    get_vector_db_manager,
    reset_vector_db_manager,
    DocumentRegistry,
    get_doc_registry,
    reset_doc_registry,
)
from .consultation import (
    # Workflow functions
    run_consultation,
    run_consultation_async,
    # API routers
    consultation_router,
    comparison_router,
    faq_router,
    # Config
    consultation_settings,
    # Utils
    request_limiter,
    get_queue_status,
)

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
    # Consultation (RAG-based support)
    "run_consultation",
    "run_consultation_async",
    "consultation_router",
    "comparison_router",
    "faq_router",
    "consultation_settings",
    "request_limiter",
    "get_queue_status",
]
