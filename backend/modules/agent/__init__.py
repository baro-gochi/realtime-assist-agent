"""Agent 모듈.

LangGraph 기반 실시간 대화 요약 에이전트를 제공합니다.

Classes:
    RoomAgent: 방별 에이전트 인스턴스
    ConversationState: 대화 상태 타입
    ContextSchema: 런타임 컨텍스트 스키마

Functions:
    create_agent_graph: LangGraph 에이전트 그래프 생성
    get_or_create_agent: 방별 에이전트 인스턴스 관리
    remove_agent: 에이전트 제거
    get_all_agents: 모든 활성 에이전트 조회

Config:
    llm_config: LLM 모델 설정
    agent_behavior_config: 에이전트 동작 설정
    redis_cache_config: Redis 캐싱 설정

Caching:
    setup_global_llm_cache: 전역 LLM 캐시 설정
    get_llm_cache: LLM 캐시 인스턴스 반환
    clear_llm_cache: 캐시 클리어
    get_cache_stats: 캐시 상태 정보

Note:
    모든 유틸리티 모듈은 utils 패키지에서 관리됩니다.
    - utils/states.py: 상태 정의
    - utils/schemas.py: Pydantic 스키마
    - utils/prompts.py: 시스템 프롬프트
    - utils/config.py: LLM/Redis 설정
    - utils/cache.py: Redis 캐싱
    - utils/nodes.py: 노드 생성 함수 + RAG 정책
"""

from .graph import create_agent_graph

# States
from .utils import (
    ConversationState,
    ContextSchema,
)

# Nodes
from .utils import (
    create_summarize_node,
    create_intent_node,
    create_sentiment_node,
    create_draft_reply_node,
    create_risk_node,
    create_rag_policy_node,
    create_faq_search_node,
    with_timing,
    # RAG 관련
    rag_policy_search,
    CustomerContext,
    PolicyRecommendation,
    RAGPolicyResult,
    COLLECTIONS,
    INTENT_COLLECTION_MAP,
    KEYWORD_COLLECTION_MAP,
)

# Config
from .utils import (
    llm_config,
    summary_llm_config,
    agent_behavior_config,
    redis_cache_config,
    LLMConfig,
    SummaryLLMConfig,
    AgentBehaviorConfig,
    RedisCacheConfig,
)

# Cache
from .utils import (
    setup_global_llm_cache,
    get_llm_cache,
    clear_llm_cache,
    get_cache_stats,
)

# Schemas
from .utils import (
    AgentBaseModel,
    SummaryResult,
    IntentResult,
    SentimentResult,
    DraftReplyResult,
    RiskResult,
    FinalConsultationSummary,
    FinalStep,
)

# Prompts
from .utils import (
    SUMMARIZE_SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    SENTIMENT_SYSTEM_PROMPT,
    DRAFT_REPLY_SYSTEM_PROMPT,
    RISK_SYSTEM_PROMPT,
    FINAL_SUMMARY_SYSTEM_PROMPT,
)

# Manager
from .manager import (
    RoomAgent,
    get_or_create_agent,
    remove_agent,
    room_agents,
)

__all__ = [
    # Graph
    "create_agent_graph",
    # States
    "ConversationState",
    "ContextSchema",
    # Nodes
    "create_summarize_node",
    "create_intent_node",
    "create_sentiment_node",
    "create_draft_reply_node",
    "create_risk_node",
    "create_rag_policy_node",
    "create_faq_search_node",
    "with_timing",
    # RAG
    "rag_policy_search",
    "CustomerContext",
    "PolicyRecommendation",
    "RAGPolicyResult",
    "COLLECTIONS",
    "INTENT_COLLECTION_MAP",
    "KEYWORD_COLLECTION_MAP",
    # Manager
    "RoomAgent",
    "get_or_create_agent",
    "remove_agent",
    "room_agents",
    # Config
    "llm_config",
    "summary_llm_config",
    "agent_behavior_config",
    "redis_cache_config",
    "LLMConfig",
    "SummaryLLMConfig",
    "AgentBehaviorConfig",
    "RedisCacheConfig",
    # Cache
    "setup_global_llm_cache",
    "get_llm_cache",
    "clear_llm_cache",
    "get_cache_stats",
    # Schemas
    "AgentBaseModel",
    "SummaryResult",
    "IntentResult",
    "SentimentResult",
    "DraftReplyResult",
    "RiskResult",
    "FinalConsultationSummary",
    "FinalStep",
    # Prompts
    "SUMMARIZE_SYSTEM_PROMPT",
    "INTENT_SYSTEM_PROMPT",
    "SENTIMENT_SYSTEM_PROMPT",
    "DRAFT_REPLY_SYSTEM_PROMPT",
    "RISK_SYSTEM_PROMPT",
    "FINAL_SUMMARY_SYSTEM_PROMPT",
]
