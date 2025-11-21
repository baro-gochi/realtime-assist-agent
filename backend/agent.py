"""LangGraph Agent for Real-time Conversation Summarization.

이 모듈은 실시간 상담 대화를 요약하는 LangGraph 에이전트를 정의합니다.

주요 기능:
    - STT transcript를 받아 대화 히스토리 누적
    - LLM을 사용하여 실시간 대화 요약 생성
    - 스트리밍 모드로 업데이트 즉시 반환

Architecture:
    StateGraph:
        START → summarize_node → END

State Structure:
    - room_name: 방 이름
    - conversation_history: [(speaker_name, text, timestamp)]
    - current_summary: 현재까지의 대화 요약

Example:
    >>> state = {
    ...     "room_name": "상담실1",
    ...     "conversation_history": [
    ...         {"speaker_name": "고객", "text": "환불하고 싶어요", "timestamp": 1234567890.0}
    ...     ],
    ...     "current_summary": ""
    ... }
    >>> async for chunk in graph.astream(state, stream_mode="updates"):
    ...     print(chunk)  # {"summarize": {"current_summary": "..."}}
"""
import logging
from typing import List, Dict, Any, Callable
from langgraph.graph import StateGraph, START, END
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.message import MessagesState

logger = logging.getLogger(__name__)

class ConversationState(MessagesState):
    """대화 상태를 나타내는 State.

    Attributes:
        room_name (str): 방 이름 (세션 식별용)
        conversation_history (List[Dict]): 대화 히스토리
            각 항목: {"speaker_name": str, "text": str, "timestamp": float}
        current_summary (str): 현재까지의 대화 요약
    """
    room_name: str
    conversation_history: List[Dict[str, Any]]
    current_summary: str


def create_summarize_node(llm: BaseChatModel) -> Callable:
    """LLM을 사용하는 summarize 노드 팩토리 함수.

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        Callable: summarize_node 함수 (LLM을 클로저로 캡처)
    """
    async def summarize_node(state: ConversationState) -> Dict[str, str]:
        """대화 요약을 생성하는 노드.

        대화 히스토리를 분석하여 LLM을 통해 요약을 생성합니다.
        실시간 상담 상황에 맞춰 간결하고 핵심적인 요약을 제공합니다.

        Args:
            state (ConversationState): 현재 대화 상태

        Returns:
            Dict[str, str]: {"current_summary": "대화 요약 텍스트"}

        Raises:
            Exception: LLM 요약 생성 실패 시

        Note:
            - 대화 히스토리가 비어있으면 빈 요약 반환
        """
        logger.info("🔵 summarize_node started")
        conversation_history = state.get("conversation_history", [])
        logger.info(f"📚 Conversation history length: {len(conversation_history)}")

        if not conversation_history:
            logger.warning("⚠️ No conversation history, returning empty summary")
            return {"current_summary": ""}

        # 대화 히스토리를 텍스트로 포맷팅
        formatted_conversation = []
        for entry in conversation_history:
            speaker = entry.get("speaker_name", "Unknown")
            text = entry.get("text", "")
            formatted_conversation.append(f"{speaker}: {text}")

        full_text = "\n".join(formatted_conversation)

        logger.info(f"📊 Generating summary for {len(conversation_history)} messages")
        logger.info(f"📝 Full text to summarize: {full_text[:200]}...")

        # LLM 요약 생성 (실패 시 예외 발생)
        summary = await _generate_llm_summary(llm, full_text)
        logger.info(f"✅ Summary generated: {summary[:100]}...")

        return {"current_summary": summary}

    return summarize_node


async def _generate_llm_summary(llm: BaseChatModel, text: str) -> str:
    """LLM을 사용하여 대화 요약 생성.

    Args:
        llm (BaseChatModel): LLM 인스턴스
        text (str): 요약할 대화 텍스트

    Returns:
        str: 생성된 요약 텍스트

    Raises:
        Exception: LLM 호출 실패 시
    """
    logger.info("🔵 _generate_llm_summary started")
    logger.info(f"📝 Text length: {len(text)} characters")

    # 시스템 프롬프트는 LLM 초기화 시 bind되었으므로, 대화 내용만 전달
    # → 토큰 수 감소 + 응답 속도 향상
    messages = [
        {
            "role": "user",
            "content": f"{text}"  # 불필요한 "다음 대화를 요약해주세요" 제거
        }
    ]

    logger.info(f"📤 Sending streaming request to LLM (system prompt already bound)")

    try:
        # 스트리밍 응답으로 첫 토큰을 빠르게 받음
        logger.info("⏳ Calling llm.astream() for faster response...")

        summary_chunks = []
        first_chunk_received = False

        async for chunk in llm.astream(messages):
            if not first_chunk_received:
                logger.info("⚡ First token received (streaming started)!")
                first_chunk_received = True

            if hasattr(chunk, 'content') and chunk.content:
                summary_chunks.append(chunk.content)

        summary = "".join(summary_chunks).strip()
        logger.info(f"✅ LLM summary generated: {summary[:100]}...")
        logger.info(f"📊 Summary length: {len(summary)} characters")
        return summary

    except Exception as e:
        logger.error(f"❌ LLM API call failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise


def create_agent_graph(llm: BaseChatModel) -> StateGraph:
    """실시간 요약 에이전트 그래프를 생성합니다.

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        StateGraph: 컴파일된 LangGraph 인스턴스

    Graph Structure:
        START → summarize_node → END

    Example:
        >>> graph = create_agent_graph(llm)
        >>> async for chunk in graph.astream(state, stream_mode="updates"):
        ...     print(chunk)
    """
    # StateGraph 생성
    graph = StateGraph(ConversationState)

    # LLM을 사용하는 summarize 노드 생성
    summarize_node = create_summarize_node(llm)

    # 노드 추가
    graph.add_node("summarize", summarize_node)

    # 엣지 연결
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", END)

    # 컴파일
    compiled_graph = graph.compile()

    logger.info("✅ Agent graph created and compiled")

    return compiled_graph