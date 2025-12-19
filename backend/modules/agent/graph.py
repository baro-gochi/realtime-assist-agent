"""LangGraph graph for 실시간 상담 지원 에이전트.

그래프 구조:
    START
      |
      +---> summarize ---------> END
      |
      +---> intent --> rag_policy ---> END  (정책 RAG 검색)
      |
      +---> faq_search --------> END  (FAQ 검색 - STT 직후 바로 실행)
      |
      +---> sentiment ---------> END
      |
      +---> draft_reply -------> END
      |
      +---> risk --------------> END

노드 정의는 utils/nodes.py 모듈에 분리되어 있습니다.
상태 정의는 utils/states.py 모듈에 분리되어 있습니다.
"""

import logging

from langgraph.graph import StateGraph, START, END
from langchain_core.language_models.chat_models import BaseChatModel

from .utils import (
    # States
    ConversationState,
    ContextSchema,
    # Node creators
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


def create_agent_graph(llm: BaseChatModel) -> StateGraph:
    """실시간 상담 지원 에이전트 그래프 생성.

    Args:
        llm: LangChain 호환 LLM 인스턴스

    Returns:
        컴파일된 StateGraph

    그래프 구조:
        START
          |
          +---> summarize ---------> END
          |
          +---> intent --> rag_policy ---> END  (정책 RAG 검색)
          |
          +---> faq_search --------> END  (FAQ 검색 - STT 직후 바로 실행)
          |
          +---> sentiment ---------> END
          |
          +---> draft_reply -------> END
          |
          +---> risk --------------> END

    FAQ 검색 최적화:
        - faq_search: START에서 바로 분기 (STT 응답 직후 실행)
        - rag_policy: intent 분석 후 실행 (의도 기반 정책 검색)
        - FAQ는 intent와 독립적으로 병렬 실행되어 빠른 응답 제공
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

    # START에서 병렬 팬아웃 (faq_search도 START에서 바로 분기)
    graph.add_edge(START, "summarize")
    graph.add_edge(START, "intent")
    graph.add_edge(START, "sentiment")
    graph.add_edge(START, "draft_reply")
    graph.add_edge(START, "risk")
    graph.add_edge(START, "faq_search")  # STT 직후 바로 FAQ 검색

    # intent -> rag_policy (의도 분석 후 정책 RAG 검색)
    graph.add_edge("intent", "rag_policy")

    # 각 노드에서 END로 "팬인"
    graph.add_edge("summarize", END)
    graph.add_edge("sentiment", END)
    graph.add_edge("draft_reply", END)
    graph.add_edge("risk", END)
    graph.add_edge("rag_policy", END)
    graph.add_edge("faq_search", END)

    compiled_graph = graph.compile()
    logger.info("[에이전트] 그래프 생성 완료 (faq_search: START에서 바로 실행)")
    return compiled_graph
