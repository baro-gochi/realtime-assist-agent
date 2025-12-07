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
    >>> from modules.agent import create_agent_graph
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
        current_summary (str): 현재까지의 대화 요약 (JSON 형식)
        last_summarized_index (int): 마지막으로 요약된 transcript 인덱스
    """
    room_name: str
    conversation_history: List[Dict[str, Any]]
    current_summary: str
    last_summarized_index: int


def create_summarize_node(llm: BaseChatModel):
    """LLM을 사용하는 summarize 노드 팩토리 함수.

    증분 요약 패턴: 새로운 transcript만 처리하여 기존 요약을 업데이트합니다.
    JSON 형식으로 엄격하게 출력합니다.

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        Callable: summarize_node 함수 (LLM을 클로저로 캡처)
    """
    async def summarize_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        """대화 요약을 증분 생성하는 노드.

        이전에 요약된 부분은 건너뛰고, 새로운 transcript만 처리하여
        기존 요약을 업데이트합니다. JSON 형식으로 출력합니다.

        Args:
            state (ConversationState): 현재 대화 상태
            runtime (Runtime[ContextSchema]): Runtime context (시스템 메시지 포함)

        Returns:
            Dict[str, Any]: {
                "current_summary": str (JSON 형식),
                "last_summarized_index": int
            }
        """
        logger.info("summarize_node started (incremental mode)")
        conversation_history = state.get("conversation_history", [])
        last_summarized_index = state.get("last_summarized_index", 0)
        current_summary = state.get("current_summary", "")

        total_count = len(conversation_history)
        logger.info(f"Total history: {total_count}, Last summarized: {last_summarized_index}")

        # 새로운 transcript가 없으면 기존 요약 반환
        if last_summarized_index >= total_count:
            logger.info("No new transcripts, returning existing summary")
            return {
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        # 새로운 transcript만 추출
        new_transcripts = conversation_history[last_summarized_index:]
        logger.info(f"Processing {len(new_transcripts)} new transcripts")

        # 새로운 대화를 텍스트로 포맷팅
        formatted_new = []
        for entry in new_transcripts:
            speaker = entry.get("speaker_name", "Unknown")
            text = entry.get("text", "")
            formatted_new.append(f"{speaker}: {text}")
        new_conversation_text = "\n".join(formatted_new)

        # 프롬프트 구성: 전체 대화 내용을 한 문장으로 요약 (덮어쓰기 방식)
        # 전체 대화를 다시 요약하여 항상 최신 한 문장 요약 유지
        all_formatted = []
        for entry in conversation_history:
            speaker = entry.get("speaker_name", "Unknown")
            text = entry.get("text", "")
            all_formatted.append(f"{speaker}: {text}")
        all_conversation_text = "\n".join(all_formatted)

        user_content = f"""전체 대화:
{all_conversation_text}

위 전체 대화 내용을 한 문장으로 요약하여 JSON으로 출력하세요.
요약은 반드시 한 문장이어야 합니다."""

        user_msg = HumanMessage(content=user_content)
        messages = [user_msg]

        # Runtime Context에서 시스템 메시지 가져오기
        if (system_message := runtime.context.system_message):
            messages = [SystemMessage(system_message)] + messages
            logger.info("System message added from runtime context")

        # LLM 호출 (스트리밍 없이 한 번에)
        logger.info("Calling LLM for incremental summary...")
        try:
            response = await llm.ainvoke(messages)
            summary = response.content.strip()
            logger.info(f"Summary generated: {summary[:100]}...")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # 에러 시 기존 요약 유지
            return {
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        # 새로운 인덱스로 업데이트
        new_last_index = total_count

        return {
            "current_summary": summary,
            "last_summarized_index": new_last_index
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
        >>> from modules.agent import create_agent_graph
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

    logger.info("Agent graph created and compiled with Runtime Context support")

    return compiled_graph
