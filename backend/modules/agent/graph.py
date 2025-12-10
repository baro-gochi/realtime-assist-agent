"""LangGraph Supervisor for 실시간 요약 + 상담 가이드.

이 모듈은 두 가지 작업을 관리하는 Supervisor 그래프를 정의합니다.
    1) summary_worker : 실시간 요약 (structured output)
    2) consultation_worker : 버튼으로 호출되는 상담 가이드 생성

핵심 포인트:
    - Runtime Context 패턴으로 시스템 메시지 주입
    - Structured Output(Pydantic/JSON Schema)으로 결과 형식 보증
    - supervisor 노드가 task에 따라 summarize/consultation으로 라우팅
"""
import logging
import time
from typing import List, Dict, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from modules.consultation.workflow import run_consultation_async

logger = logging.getLogger(__name__)


# JSON Schema for Structured Output
CONVERSATION_SUMMARY_SCHEMA = {
    "title": "ConversationSummary",
    "description": "실시간 대화 요약 스키마",
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "현재 대화의 한 문장 요약 (20자 이내)"
        },
        "customer_issue": {
            "type": "string",
            "description": "고객이 제기한 문의/이슈 한 줄 요약"
        },
        "agent_action": {
            "type": "string",
            "description": "상담원의 대응/조치 한 줄 요약"
        }
    },
    "required": ["summary", "customer_issue", "agent_action"]
}


class SummaryResult(BaseModel):
    """실시간 요약 결과 구조."""
    summary: str = Field(default="", description="대화 한 줄 요약")
    customer_issue: str = Field(default="", description="고객 문의 요약")
    agent_action: str = Field(default="", description="상담원 조치 요약")


class ConsultationResult(BaseModel):
    """버튼으로 요청되는 상담 가이드 결과 구조."""
    guide: List[str] = Field(default_factory=list, description="단계별 상담 가이드")
    recommendations: List[str] = Field(default_factory=list, description="추가 제안 사항")
    citations: List[str] = Field(default_factory=list, description="참조 문서/조항 식별자")
    generated_at: float = Field(default_factory=time.time, description="UNIX timestamp")


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
    summary_result: Dict[str, Any] | None
    consultation_result: Dict[str, Any] | None
    task: str | None
    user_options: Dict[str, Any] | None


def create_summarize_node(llm: BaseChatModel):
    """LLM을 사용하는 summarize 노드 팩토리 함수.

    with_structured_output을 사용하여 JSON Schema로 출력 형식을 강제합니다.

    Args:
        llm (BaseChatModel): 초기화된 LLM 인스턴스

    Returns:
        Callable: summarize_node 함수 (structured LLM을 클로저로 캡처)
    """
    # Structured Output LLM 생성
    structured_llm = llm.with_structured_output(
        CONVERSATION_SUMMARY_SCHEMA,
        method="json_schema",
    )
    logger.info("Structured LLM created with JSON Schema")

    async def summarize_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        """대화 요약을 생성하는 노드 (Structured Output 사용).

        with_structured_output을 사용하여 항상 유효한 JSON을 반환합니다.

        Args:
            state (ConversationState): 현재 대화 상태
            runtime (Runtime[ContextSchema]): Runtime context (시스템 메시지 포함)

        Returns:
            Dict[str, Any]: {
                "summary_result": SummaryResult,
                "current_summary": str (JSON 형식),
                "last_summarized_index": int
            }
        """
        logger.info("summarize_node started (structured output mode)")
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

        # 전체 대화를 텍스트로 포맷팅 (최근 20개만 사용)
        recent_history = conversation_history[-20:]
        formatted_lines = []
        for entry in recent_history:
            speaker = entry.get("speaker_name", "Unknown")
            text = entry.get("text", "")
            formatted_lines.append(f"{speaker}: {text}")
        conversation_text = "\n".join(formatted_lines)

        # 프롬프트 구성
        user_content = f"""다음 고객 상담 대화를 분석하세요:

{conversation_text}

위 대화 내용을 요약해주세요."""

        messages = [HumanMessage(content=user_content)]

        # Runtime Context에서 시스템 메시지 가져오기
        if (system_message := runtime.context.system_message):
            messages = [SystemMessage(content=system_message)] + messages
            logger.debug("System message added from runtime context")

        # Structured LLM 호출
        logger.info("Calling structured LLM for summary...")
        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            summary_model = SummaryResult(**result)
            # JSON 문자열(레거시) 유지
            summary_json = summary_model.model_dump_json(ensure_ascii=False)
            logger.info(f"Structured summary generated: {summary_json[:100]}...")
        except Exception as e:
            logger.error(f"Structured LLM call failed: {e}")
            # 에러 시 기존 요약 유지
            return {
                "summary_result": state.get("summary_result", {}),
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        # 새로운 인덱스로 업데이트
        new_last_index = total_count

        return {
            "summary_result": summary_model.model_dump(),
            "current_summary": summary_json,
            "last_summarized_index": new_last_index
        }

    return summarize_node


def create_consultation_node():
    """consultation_worker 노드: 상담 워크플로우를 호출."""

    async def consultation_node(state: ConversationState, runtime: Runtime[ContextSchema]) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])

        # 입력 요약: 최근 30개 발화 연결
        recent_history = conversation_history[-30:]
        formatted_lines = [f"{item.get('speaker_name', 'Unknown')}: {item.get('text', '')}" for item in recent_history]
        summary_input = "\n".join(formatted_lines) if formatted_lines else "대화 없음"

        logger.info("Running consultation workflow...")
        try:
            result = await run_consultation_async(summary_input)
            guide_text = result.get("response_guide", "") or ""
            # 간단한 분리: 줄 단위 bullet
            guide_lines = [line.strip() for line in guide_text.splitlines() if line.strip()]
            consultation_result = ConsultationResult(
                guide=guide_lines,
                recommendations=[],
                citations=[],
                generated_at=time.time(),
            )
            return {"consultation_result": consultation_result.model_dump()}
        except Exception as e:
            logger.error(f"Consultation workflow failed: {e}", exc_info=True)
            return {"consultation_result": {"error": str(e)}}

    return consultation_node


def create_supervisor_graph(llm: BaseChatModel) -> StateGraph:
    """요약/상담 가이드 두 작업을 관리하는 Supervisor 그래프."""

    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema
    )

    summarize_node = create_summarize_node(llm)
    consultation_node = create_consultation_node()

    def route_task(state: ConversationState):
        task = state.get("task", "summary") or "summary"
        if task not in {"summary", "consultation"}:
            return "summary"
        return task

    graph.add_node("route_task", lambda state: state)
    graph.add_node("summarize", summarize_node)
    graph.add_node("consultation", consultation_node)

    graph.add_edge(START, "route_task")
    graph.add_conditional_edges(
        "route_task",
        route_task,
        {
            "summary": "summarize",
            "consultation": "consultation",
        }
    )
    graph.add_edge("summarize", END)
    graph.add_edge("consultation", END)

    compiled_graph = graph.compile()
    logger.info("Supervisor graph created and compiled")
    return compiled_graph


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
    # 기존 API 호환을 위해 supervisor 그래프를 반환합니다.
    return create_supervisor_graph(llm)
