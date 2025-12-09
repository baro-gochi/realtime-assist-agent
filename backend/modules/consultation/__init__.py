"""Consultation module for CS representative support.

RAG-based consultation support system using LangGraph workflows.

Usage:
    from modules.consultation import run_consultation_async
    from modules.consultation import consultation_router

    # Run consultation workflow
    result = await run_consultation_async("Customer inquiry about contract termination")

    # Include routers in FastAPI app
    app.include_router(consultation_router)
"""

# Workflow functions
from .workflow import (
    run_consultation,
    run_consultation_async,
    run_direct_search,
    run_direct_search_async,
    run_direct_keyword_guide,
    run_direct_keyword_guide_async,
    run_keyword_extraction_guide,
    run_keyword_extraction_guide_async,
    run_direct_full_guide,
    run_direct_full_guide_async,
    reset_agent_app,
    get_agent_app,
    get_direct_search_app,
)

# State
from .state import AgentState, create_initial_state

# Nodes
from .nodes import (
    analyzer_node,
    search_node,
    response_generator_node,
    direct_embedding_search_node,
    keyword_guide_node,
    faq_search_node,
)

# Models
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

# Utils
from .utils import request_limiter, get_queue_status

# Config
from .config import consultation_settings

# API Routers
from .api import consultation_router, comparison_router, faq_router

__all__ = [
    # Workflow
    "run_consultation",
    "run_consultation_async",
    "run_direct_search",
    "run_direct_search_async",
    "run_direct_keyword_guide",
    "run_direct_keyword_guide_async",
    "run_keyword_extraction_guide",
    "run_keyword_extraction_guide_async",
    "run_direct_full_guide",
    "run_direct_full_guide_async",
    "reset_agent_app",
    "get_agent_app",
    "get_direct_search_app",
    # State
    "AgentState",
    "create_initial_state",
    # Nodes
    "analyzer_node",
    "search_node",
    "response_generator_node",
    "direct_embedding_search_node",
    "keyword_guide_node",
    "faq_search_node",
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
    # Utils
    "request_limiter",
    "get_queue_status",
    # Config
    "consultation_settings",
    # API Routers
    "consultation_router",
    "comparison_router",
    "faq_router",
]
