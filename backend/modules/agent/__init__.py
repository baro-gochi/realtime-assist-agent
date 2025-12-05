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
    prompt_config: 시스템 프롬프트 설정
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
    get_all_agents,
    room_agents,
)
from .config import (
    llm_config,
    agent_behavior_config,
    LLMConfig,
    AgentBehaviorConfig,
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
    "get_all_agents",
    "room_agents",
    # Config
    "llm_config",
    "agent_behavior_config",
    "prompt_config",
    "LLMConfig",
    "AgentBehaviorConfig",
]
