"""LangGraph 테스트용 그래프.

이 파일은 그래프 구조 변경 및 tool_calling 테스트 용도입니다.
프로덕션 코드(graph.py)에 영향을 주지 않고 실험할 수 있습니다.

LangGraph Server에서 직접 로드 가능 (절대 import 사용).

테스트 가능 항목:
    - 그래프 구조 변경 (노드 순서, 엣지 연결)
    - Tool Calling 통합
    - 새로운 노드 추가
    - 조건부 엣지 (conditional_edge)
    - 서브그래프 구성

현재 구조 (graph.py와 동일):
    START
      |
      +---> summarize ---------> END
      |
      +---> intent --> rag_policy ---> END
      |
      +---> faq_search --------> END
      |
      +---> sentiment ---------> END
      |
      +---> draft_reply -------> END
      |
      +---> risk --------------> END
"""

import logging
import sys
from pathlib import Path
from typing import Literal

# backend 디렉토리를 sys.path에 추가 (절대 import 지원)
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool

# 절대 import 사용
from modules.agent.utils.states import ConversationState, ContextSchema
from modules.agent.utils.nodes import (
    with_timing,
    create_summarize_node,
    create_intent_node,
    create_sentiment_node,
    create_draft_reply_node,
    create_risk_node,
    create_rag_policy_node,
    create_faq_search_node,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions (테스트용)
# =============================================================================

@tool
def search_policy(query: str, category: str = "all") -> str:
    """정책 문서를 검색합니다.

    Args:
        query: 검색 쿼리
        category: 카테고리 (mobile, internet, tv, bundle, penalty, membership, all)

    Returns:
        검색 결과 문자열
    """
    # TODO: 실제 RAG 검색 로직 연동
    return f"[정책 검색 결과] query='{query}', category='{category}'"


@tool
def search_faq(question: str) -> str:
    """FAQ를 검색합니다.

    Args:
        question: 고객 질문

    Returns:
        FAQ 검색 결과
    """
    # TODO: 실제 FAQ 검색 로직 연동
    return f"[FAQ 검색 결과] question='{question}'"


@tool
def get_customer_info(customer_id: str) -> str:
    """고객 정보를 조회합니다.

    Args:
        customer_id: 고객 ID

    Returns:
        고객 정보 문자열
    """
    # TODO: 실제 고객 정보 조회 연동
    return f"[고객 정보] customer_id='{customer_id}'"


# 테스트용 도구 목록
TEST_TOOLS = [search_policy, search_faq, get_customer_info]


# =============================================================================
# Graph Factory Functions
# =============================================================================

def create_test_graph(llm: BaseChatModel) -> StateGraph:
    """테스트용 에이전트 그래프 생성 (graph.py와 동일한 구조).

    Args:
        llm: LangChain 호환 LLM 인스턴스

    Returns:
        컴파일된 StateGraph
    """
    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema
    )

    # 노드 생성 (with_timing 래퍼로 실행 시간 측정)
    summarize_node = with_timing("summarize", create_summarize_node(llm))
    intent_node = with_timing("intent", create_intent_node(llm))
    sentiment_node = with_timing("sentiment", create_sentiment_node(llm))
    draft_reply_node = with_timing("draft_reply", create_draft_reply_node(llm))
    risk_node = with_timing("risk", create_risk_node(llm))
    rag_policy_node = with_timing("rag_policy", create_rag_policy_node())
    faq_search_node = with_timing("faq_search", create_faq_search_node())

    # 노드 추가
    graph.add_node("summarize", summarize_node)
    graph.add_node("intent", intent_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("draft_reply", draft_reply_node)
    graph.add_node("risk", risk_node)
    graph.add_node("rag_policy", rag_policy_node)
    graph.add_node("faq_search", faq_search_node)

    # START에서 병렬 팬아웃
    graph.add_edge(START, "summarize")
    graph.add_edge(START, "intent")
    graph.add_edge(START, "sentiment")
    graph.add_edge(START, "draft_reply")
    graph.add_edge(START, "risk")
    graph.add_edge(START, "faq_search")

    # intent -> rag_policy
    graph.add_edge("intent", "rag_policy")

    # 각 노드에서 END로 팬인
    graph.add_edge("summarize", END)
    graph.add_edge("sentiment", END)
    graph.add_edge("draft_reply", END)
    graph.add_edge("risk", END)
    graph.add_edge("rag_policy", END)
    graph.add_edge("faq_search", END)

    compiled_graph = graph.compile()
    logger.info("[테스트 그래프] 기본 구조 생성 완료")
    return compiled_graph


def create_tool_calling_graph(llm: BaseChatModel) -> StateGraph:
    """Tool Calling 테스트용 그래프.

    구조:
        START --> agent --> should_continue? --> tools --> agent (loop)
                                             --> END

    Args:
        llm: LangChain 호환 LLM 인스턴스 (tool calling 지원 필요)

    Returns:
        컴파일된 StateGraph
    """
    # LLM에 도구 바인딩
    llm_with_tools = llm.bind_tools(TEST_TOOLS)

    def agent_node(state: ConversationState):
        """에이전트 노드 - LLM 호출 및 tool call 결정."""
        messages = state.get("messages", [])
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: ConversationState) -> Literal["tools", "end"]:
        """Tool call이 필요한지 판단."""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None

        if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    # 그래프 구성
    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema
    )

    # 노드 추가
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TEST_TOOLS))

    # 엣지 연결
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )
    graph.add_edge("tools", "agent")

    compiled_graph = graph.compile()
    logger.info("[테스트 그래프] Tool Calling 구조 생성 완료")
    return compiled_graph


def create_sequential_graph(llm: BaseChatModel) -> StateGraph:
    """순차 실행 테스트용 그래프.

    구조 (병렬 대신 순차 실행):
        START --> intent --> sentiment --> summarize --> draft_reply --> END
                    |
                    +--> rag_policy --> END

    Args:
        llm: LangChain 호환 LLM 인스턴스

    Returns:
        컴파일된 StateGraph
    """
    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema
    )

    # 노드 생성
    intent_node = with_timing("intent", create_intent_node(llm))
    sentiment_node = with_timing("sentiment", create_sentiment_node(llm))
    summarize_node = with_timing("summarize", create_summarize_node(llm))
    draft_reply_node = with_timing("draft_reply", create_draft_reply_node(llm))
    rag_policy_node = with_timing("rag_policy", create_rag_policy_node())

    # 노드 추가
    graph.add_node("intent", intent_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("draft_reply", draft_reply_node)
    graph.add_node("rag_policy", rag_policy_node)

    # 순차 실행 엣지
    graph.add_edge(START, "intent")
    graph.add_edge("intent", "sentiment")
    graph.add_edge("intent", "rag_policy")  # intent에서 분기
    graph.add_edge("sentiment", "summarize")
    graph.add_edge("summarize", "draft_reply")
    graph.add_edge("draft_reply", END)
    graph.add_edge("rag_policy", END)

    compiled_graph = graph.compile()
    logger.info("[테스트 그래프] 순차 실행 구조 생성 완료")
    return compiled_graph


# =============================================================================
# Convenience alias
# =============================================================================

# 기본 테스트 그래프 (graph.py와 동일)
create_agent_graph_test = create_test_graph


# =============================================================================
# LangGraph Server용 컴파일된 그래프 인스턴스
# =============================================================================

def _create_default_graph():
    """LangGraph 서버용 기본 그래프 생성."""
    from langchain.chat_models import init_chat_model
    from modules.agent.utils.config import llm_config
    from modules.agent.utils.cache import setup_global_llm_cache

    # 캐시 설정
    setup_global_llm_cache()

    # LLM 초기화
    logger.info(f"[LangGraph Server] LLM 초기화: {llm_config.MODEL}")
    llm = init_chat_model(
        llm_config.MODEL,
        temperature=llm_config.TEMPERATURE,
    )

    return create_test_graph(llm)


# LangGraph 서버가 로드할 컴파일된 그래프 인스턴스
# langgraph.json에서 "agent": "./graph_test.py:graph" 로 참조
graph = _create_default_graph()
