"""LangGraph State 정의 모듈.

대화 상태(ConversationState)와 런타임 컨텍스트(ContextSchema)를 정의합니다.
"""

from typing import List, Dict, Any
from dataclasses import dataclass

from langgraph.graph.message import MessagesState


@dataclass
class ContextSchema:
    """에이전트 생성 시 설정하는 Runtime Context.

    Attributes:
        static_system_prefix (str | None): 정적 시스템 프롬프트 (캐싱 대상)
            - 기본 역할 정의 + 고객 정보 + 상담 이력
            - 모든 노드에서 첫 번째 메시지로 동일하게 사용
            - OpenAI 백엔드에서 자동 캐싱되어 TTFT 감소

        system_message (str | None): 기존 호환용 필드 (deprecated, static_system_prefix 사용 권장)
    """
    static_system_prefix: str | None = None
    system_message: str | None = None  # 하위 호환성 유지

    def get_system_message(self) -> str | None:
        """정적 시스템 메시지 반환 (우선순위: static_system_prefix > system_message)."""
        return self.static_system_prefix or self.system_message


class ConversationState(MessagesState):
    """대화 상태를 나타내는 State (MessagesState 상속).

    기본 필드:
        messages: 메시지 히스토리 (자동 관리)

    커스텀 필드:
        room_name (str)
        conversation_history (List[Dict])
        current_summary (str)
        last_summarized_index (int)
        summary_result (Dict | None)
        customer_info (Dict | None)
        consultation_history (List[Dict])

        intent_result (Dict | None)
        sentiment_result (Dict | None)
        draft_replies (Dict | None)
        risk_result (Dict | None)
        rag_policy_result (Dict | None): RAG 정책 검색 결과

        has_new_customer_turn (bool): 새로운 고객 발화가 있는지 여부
        last_intent_index (int): 마지막으로 의도 분석한 대화 인덱스
        last_sentiment_index (int): 마지막으로 감정 분석한 대화 인덱스
        last_draft_index (int): 마지막으로 응답 초안 생성한 대화 인덱스
        last_risk_index (int): 마지막으로 위험 감지한 대화 인덱스
        last_rag_index (int): 마지막으로 RAG 검색한 대화 인덱스
    """
    room_name: str
    conversation_history: List[Dict[str, Any]]
    current_summary: str
    last_summarized_index: int
    summary_result: Dict[str, Any] | None
    customer_info: Dict[str, Any] | None
    consultation_history: List[Dict[str, Any]]

    intent_result: Dict[str, Any] | None
    sentiment_result: Dict[str, Any] | None
    draft_replies: Dict[str, Any] | None
    risk_result: Dict[str, Any] | None
    rag_policy_result: Dict[str, Any] | None
    faq_result: Dict[str, Any] | None  # FAQ semantic cache 검색 결과

    has_new_customer_turn: bool
    last_intent_index: int
    last_sentiment_index: int
    last_draft_index: int
    last_risk_index: int
    last_rag_index: int
    last_faq_index: int  # 마지막으로 FAQ 검색한 대화 인덱스
    last_rag_intent: str  # 마지막으로 RAG 검색한 의도 라벨 (중복 방지)
    last_faq_query: str  # 마지막으로 FAQ 검색한 쿼리 (중복 방지)
    shown_faq_ids: List[str]  # 이미 보여준 FAQ ID 목록 (중복 방지)
