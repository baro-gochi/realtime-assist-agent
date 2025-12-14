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
"""

from .graph import (
    create_agent_graph,
    ConversationState,
    ContextSchema,
    create_summarize_node,
)
from .manager import (
    RoomAgent,
    get_or_create_agent,
    remove_agent,
    room_agents,
)
from .config import (
    llm_config,
    agent_behavior_config,
    redis_cache_config,
    LLMConfig,
    AgentBehaviorConfig,
    RedisCacheConfig,
)
from .cache import (
    setup_global_llm_cache,
    get_llm_cache,
    clear_llm_cache,
    get_cache_stats,
)

__all__ = [
    # Graph
    "create_agent_graph",
    "ConversationState",
    "ContextSchema",
    "create_summarize_node",
    # Manager
    "RoomAgent",
    "get_or_create_agent",
    "remove_agent",
    "room_agents",
    # Config
    "llm_config",
    "agent_behavior_config",
    "redis_cache_config",
    "LLMConfig",
    "AgentBehaviorConfig",
    "RedisCacheConfig",
    # Cache
    "setup_global_llm_cache",
    "get_llm_cache",
    "clear_llm_cache",
    "get_cache_stats",
]
