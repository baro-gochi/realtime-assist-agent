"""Consultation module for CS representative support.

RAG-based consultation support system using LangGraph workflows.

NOTE: 순환 import 방지를 위해 workflow, nodes는 여기서 재export하지 않습니다.
      직접 import하세요:
      - from modules.consultation.workflow import run_consultation_async
      - from modules.consultation.nodes import analyzer_node

Usage:
    # Config (안전하게 import 가능)
    from modules.consultation import consultation_settings

    # API routers (안전하게 import 가능)
    from modules.consultation import consultation_router

    # Workflow 함수들 (직접 import 권장)
    from modules.consultation.workflow import run_consultation_async
"""

# Config (의존성 없음 - 안전)
from .config import consultation_settings

# Utils (의존성 없음 - 안전)
from .utils import request_limiter, get_queue_status

# Models (의존성 없음 - 안전)
from .models import (
    DocumentInfo,
    HealthStatus,
    ErrorResponse,
    QueueStatusResponse,
    ConsultationRequest,
    ConsultationResponse,
    ComparisonRequest,
    DirectSearchResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse,
)

# State (의존성 없음 - 안전)
from .state import AgentState, create_initial_state

# API Routers는 lazy import로 제공
# (routers가 workflow를 import하므로 순환 가능성 있음)
def _get_routers():
    """Lazy import for API routers."""
    from .api import consultation_router, comparison_router, faq_router
    return consultation_router, comparison_router, faq_router


# 편의를 위한 속성 접근자 (lazy import)
def __getattr__(name):
    """Lazy import for heavy modules to avoid circular imports."""
    # Workflow functions
    if name in (
        "run_consultation", "run_consultation_async",
        "run_direct_search", "run_direct_search_async",
        "run_direct_keyword_guide", "run_direct_keyword_guide_async",
        "run_keyword_extraction_guide", "run_keyword_extraction_guide_async",
        "run_direct_full_guide", "run_direct_full_guide_async",
        "reset_agent_app", "get_agent_app", "get_direct_search_app",
    ):
        from . import workflow
        return getattr(workflow, name)

    # Node functions
    if name in (
        "analyzer_node", "search_node", "response_generator_node",
        "direct_embedding_search_node", "keyword_guide_node", "faq_search_node",
    ):
        from . import nodes
        return getattr(nodes, name)

    # API routers
    if name in ("consultation_router", "comparison_router", "faq_router"):
        from . import api
        return getattr(api, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Config
    "consultation_settings",
    # Utils
    "request_limiter",
    "get_queue_status",
    # Models
    "DocumentInfo",
    "HealthStatus",
    "ErrorResponse",
    "QueueStatusResponse",
    "ConsultationRequest",
    "ConsultationResponse",
    "ComparisonRequest",
    "DirectSearchResponse",
    "KeywordGuideResponse",
    "DirectFullGuideResponse",
    # State
    "AgentState",
    "create_initial_state",
    # Lazy-loaded (via __getattr__)
    "run_consultation",
    "run_consultation_async",
    "consultation_router",
    "comparison_router",
    "faq_router",
]
