"""LangGraph Agent for Real-time Conversation Summarization.

이 모듈은 실시간 상담 대화를 요약하는 LangGraph 에이전트를 정의합니다.

주요 기능:
    - STT transcript를 받아 대화 히스토리 누적
    - LLM을 사용하여 실시간 대화 요약 생성
    - 스트리밍 모드로 업데이트 즉시 반환
    - Runtime Context 패턴으로 시스템 메시지 한 번만 설정

Architecture:
    StateGraph with Runtime Context:
        START → summarize_node → END
        - Runtime Context: 시스템 메시지를 에이전트 생성 시 고정
        - MessagesState: 메시지 히스토리 자동 관리

State Structure:
    - room_name: 방 이름
    - conversation_history: [(speaker_name, text, timestamp)]
    - current_summary: 현재까지의 대화 요약
    - messages: MessagesState가 자동 관리하는 메시지 히스토리

Example:
    >>> graph = create_agent_graph(llm)
    >>> async for chunk in graph.astream(
    ...     state,
    ...     stream_mode="updates",
    ...     context={"system_message": "고객 상담 대화를 요약하세요."}
    ... ):
    ...     print(chunk)  # {"summarize": {"current_summary": "..."}}
"""
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


@dataclass
class ContextSchema:
    """에이전트 생성 시 설정하는 Runtime Context.

    Attributes:
        system_message (str | None): 시스템 프롬프트 (에이전트 생성 시 고정)
    """
    system_message: str | None = None


class ConversationState(MessagesState):
    """대화 상태를 나타내는 State (MessagesState 상속).

    MessagesState 기본 필드:
        messages: 메시지 히스토리 (자동 관리)

    추가 커스텀 필드:
        room_name (str): 방 이름 (세션 식별용)
        conversation_history (List[Dict]): 대화 히스토리
            각 항목: {"speaker_name": str, "text": str, "timestamp": float}
        current_summary (str): 현재까지의 대화 요약
    """
    room_name: str
    conversation_history: List[Dict[str, Any]]
    current_summary: str


def create_summarize_node(llm: BaseChatModel):
    """LLM을 사용하는 summarize 노드 팩토리 함수.

    Runtime Context 패턴을 사용하여 시스템 메시지를 자동으로 추가합니다.

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        Callable: summarize_node 함수 (LLM을 클로저로 캡처)
    """
    async def summarize_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        """대화 요약을 생성하는 노드 (Runtime Context 패턴).

        대화 히스토리를 분석하여 LLM을 통해 요약을 생성합니다.
        Runtime Context에서 시스템 메시지를 자동으로 가져와 적용합니다.

        Args:
            state (ConversationState): 현재 대화 상태
            runtime (Runtime[ContextSchema]): Runtime context (시스템 메시지 포함)

        Returns:
            Dict[str, Any]: {
                "messages": [AIMessage],  # LLM 응답 메시지
                "current_summary": str    # 요약 텍스트
            }

        Raises:
            Exception: LLM 요약 생성 실패 시

        Note:
            - 대화 히스토리가 비어있으면 빈 요약 반환
            - 시스템 메시지는 runtime.context.system_message에서 자동으로 가져옴
        """
        logger.info("🔵 summarize_node started")
        conversation_history = state.get("conversation_history", [])
        logger.info(f"📚 Conversation history length: {len(conversation_history)}")

        if not conversation_history:
            logger.warning("⚠️ No conversation history, returning empty summary")
            return {
                "messages": [],
                "current_summary": ""
            }

        # 대화 히스토리를 텍스트로 포맷팅
        formatted_conversation = []
        for entry in conversation_history:
            speaker = entry.get("speaker_name", "Unknown")
            text = entry.get("text", "")
            formatted_conversation.append(f"{speaker}: {text}")

        conversation_text = "\n".join(formatted_conversation)

        logger.info(f"📊 Generating summary for {len(conversation_history)} messages")
        logger.info(f"📝 Conversation text: {conversation_text[:200]}...")

        # 사용자 메시지 생성
        user_msg = HumanMessage(content=conversation_text)
        messages = [user_msg]

        # Runtime Context에서 시스템 메시지 가져오기
        if (system_message := runtime.context.system_message):
            # 시스템 메시지를 messages 앞에 추가
            messages = [SystemMessage(system_message)] + messages
            logger.info("📝 System message added from runtime context")
        else:
            logger.warning("⚠️ No system message in runtime context")

        # LLM 호출 (스트리밍)
        logger.info("⏳ Calling LLM for summary...")
        summary_chunks = []
        first_chunk_received = False

        async for chunk in llm.astream(messages):
            if not first_chunk_received:
                logger.info("⚡ First token received (streaming started)!")
                first_chunk_received = True

            # 청크 전체 구조 디버깅 (reasoning 모델 분석용)
            logger.debug(f"🔍 Chunk: {chunk}")
            logger.debug(f"🔍 Chunk.__dict__: {chunk.__dict__ if hasattr(chunk, '__dict__') else 'N/A'}")

            # additional_kwargs 확인
            if hasattr(chunk, 'additional_kwargs'):
                logger.debug(f"🔍 additional_kwargs: {chunk.additional_kwargs}")

            if hasattr(chunk, 'content') and chunk.content:
                logger.debug(f"📝 Appending content: {chunk.content}")
                summary_chunks.append(chunk.content)

        summary = "".join(summary_chunks).strip()
        logger.info(f"✅ Summary generated ({len(summary_chunks)} chunks): {summary[:100]}...")

        # MessagesState가 자동으로 messages를 관리
        return {
            "messages": [HumanMessage(content=conversation_text)],  # 대화 내용 저장
            "current_summary": summary
        }

    return summarize_node


def create_agent_graph(llm: BaseChatModel) -> StateGraph:
    """실시간 요약 에이전트 그래프를 생성합니다 (Runtime Context 패턴).

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        StateGraph: 컴파일된 LangGraph 인스턴스 (Runtime Context 지원)

    Graph Structure:
        START → summarize_node → END

    Runtime Context:
        - ContextSchema를 통해 시스템 메시지를 에이전트 생성 시 고정
        - graph.astream(..., context={"system_message": "..."})로 전달

    Example:
        >>> graph = create_agent_graph(llm)
        >>> async for chunk in graph.astream(
        ...     state,
        ...     stream_mode="updates",
        ...     context={"system_message": "고객 상담 대화를 요약하세요."}
        ... ):
        ...     print(chunk)
    """
    # StateGraph 생성 (context_schema 지정)
    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema  # Runtime Context 패턴 적용
    )

    # LLM을 사용하는 summarize 노드 생성
    summarize_node = create_summarize_node(llm)

    # 노드 추가
    graph.add_node("summarize", summarize_node)

    # 엣지 연결
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", END)

    # 컴파일
    compiled_graph = graph.compile()

    logger.info("✅ Agent graph created and compiled with Runtime Context support")

    return compiled_graph