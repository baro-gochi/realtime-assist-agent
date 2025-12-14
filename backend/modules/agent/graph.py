"""LangGraph graph for 실시간 상담 지원 에이전트 (요약 + 의도 + 감정 + 응답초안 + 위험경고 + RAG Tool Calling)."""
import logging
import time
from typing import List, Dict, Any, Callable, Awaitable, Literal, Annotated
from dataclasses import dataclass
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import MessagesState
from langgraph.runtime import Runtime
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from modules.shared import SummaryResult

logger = logging.getLogger(__name__)

# ---------- JSON Schema 정의 ----------

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

INTENT_SCHEMA = {
    "title": "ConversationIntent",
    "description": "현재 턴 기준 핵심 의도 파악",
    "type": "object",
    "properties": {
        "intent_label": {
            "type": "string",
            "description": "핵심 의도 라벨 (예: '요금제 변경', 'PASS 보안 문의')"
        },
        "intent_confidence": {
            "type": "number",
            "description": "의도에 대한 확신도 (0~1)"
        },
        "intent_explanation": {
            "type": "string",
            "description": "의도 판단 근거를 한두 문장으로 설명"
        }
    },
    "required": ["intent_label"]
}

SENTIMENT_SCHEMA = {
    "title": "ConversationSentiment",
    "description": "현재 고객 감정 상태 분석",
    "type": "object",
    "properties": {
        "sentiment_label": {
            "type": "string",
            "description": "감정 라벨 (예: '불안', '혼란', '분노', '안정')"
        },
        "sentiment_score": {
            "type": "number",
            "description": "해당 감정의 강도 (0~1)"
        },
        "sentiment_explanation": {
            "type": "string",
            "description": "감정 판단 근거 한두 문장"
        }
    },
    "required": ["sentiment_label"]
}

DRAFT_REPLY_SCHEMA = {
    "title": "DraftReplySuggestions",
    "description": "상담사가 바로 읽고 쓸 수 있는 응답 초안",
    "type": "object",
    "properties": {
        "short_reply": {
            "type": "string",
            "description": "짧고 단호한 한 줄 답변 초안 (1-2문장)"
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "응답에 포함할 핵심 키워드 리스트 (3-5개)"
        }
    },
    "required": ["short_reply", "keywords"]
}

RISK_SCHEMA = {
    "title": "RiskDetection",
    "description": "위험/리스크 관련 플래그",
    "type": "object",
    "properties": {
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "감지된 리스크 코드 리스트 (예: 'security_concern', 'cancellation_risk')"
        },
        "risk_explanation": {
            "type": "string",
            "description": "왜 위험 요소로 판단했는지 설명"
        }
    },
    "required": ["risk_flags"]
}

FINAL_SUMMARY_SCHEMA = {
    "title": "FinalConsultationSummary",
    "description": "상담 종료 시 최종 요약 (구조화된 형식)",
    "type": "object",
    "properties": {
        "consultation_type": {
            "type": "string",
            "description": "상담 유형 (예: '요금 문의', '해지 상담', '기술 지원')"
        },
        "customer_issue": {
            "type": "string",
            "description": "고객이 제기한 핵심 문의/이슈"
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer", "description": "순서 번호"},
                    "action": {"type": "string", "description": "수행된 조치/진행 내용"}
                },
                "required": ["order", "action"]
            },
            "description": "상담 진행 과정을 순서대로 정리"
        },
        "resolution": {
            "type": "string",
            "description": "최종 해결 결과 또는 후속 조치 필요 사항"
        },
        "customer_sentiment": {
            "type": "string",
            "description": "상담 종료 시 고객 감정 상태 (예: '만족', '불만', '보류')"
        }
    },
    "required": ["consultation_type", "customer_issue", "steps", "resolution"]
}

FINAL_SUMMARY_SYSTEM_PROMPT = """당신은 KT 고객센터 상담 기록 정리 AI입니다.

## 역할
완료된 상담 대화를 분석하여 **구조화된 최종 요약**을 생성합니다.

## 작업 지시사항
1. 전체 대화를 분석하여 상담 유형을 분류하세요
2. 고객의 핵심 문의/이슈를 명확하게 정리하세요
3. 상담 진행 과정을 **순서대로** 정리하세요 (각 단계별 주요 내용)
4. 최종 해결 결과 또는 후속 조치가 필요한 사항을 기록하세요
5. 상담 종료 시 고객의 감정 상태를 평가하세요

## 출력 형식
- consultation_type: 상담 유형 (요금 문의, 해지 상담, 기술 지원, 서비스 가입 등)
- customer_issue: 고객이 제기한 핵심 문의/이슈
- steps: 상담 진행 과정 배열 [{order: 1, action: "..."}, ...]
- resolution: 최종 해결 결과 또는 후속 조치 필요 사항
- customer_sentiment: 종료 시 고객 감정 (만족/불만/보류/미확인)

## 예시 출력
{
  "consultation_type": "요금제 변경",
  "customer_issue": "현재 요금제에서 더 저렴한 요금제로 변경 문의",
  "steps": [
    {"order": 1, "action": "고객 본인 확인 완료"},
    {"order": 2, "action": "현재 요금제 및 사용량 확인"},
    {"order": 3, "action": "5G 다이렉트 요금제 안내"},
    {"order": 4, "action": "요금제 변경 신청 접수"}
  ],
  "resolution": "5G 다이렉트 49,000원 요금제로 변경 완료, 다음 달부터 적용",
  "customer_sentiment": "만족"
}"""


# ---------- 노드별 정적 시스템 프롬프트 (OpenAI Prompt Caching 대상) ----------
# 각 노드의 지시사항을 SystemMessage에 포함하여 캐싱 효과 극대화
# 변수(대화 내용)만 HumanMessage로 전달

SUMMARIZE_SYSTEM_PROMPT = """당신은 KT 고객센터 실시간 상담 지원 AI입니다.

## 역할
고객과 상담사 간의 실시간 대화를 분석하여 **증분 요약**을 생성합니다.

## 작업 지시사항
1. 이전 요약과 새로 추가된 대화를 통합하여 하나의 완성된 요약을 작성하세요
2. 요약은 상담사가 한눈에 파악할 수 있도록 간결하게 작성합니다

## 출력 형식
- summary: 현재까지의 대화를 한 문장으로 요약 (20자 이내)
- customer_issue: 고객이 제기한 핵심 문의/이슈 한 줄 요약
- agent_action: 상담원의 대응/조치 한 줄 요약

## KT 도메인 지식
- 요금제: 5G/LTE/다이렉트/시니어 요금제
- 부가서비스: PASS 인증, 스팸차단, 데이터쉐어링, 로밍
- 결합상품: 인터넷+TV+모바일 결합, 가족결합
- 멤버십: VIP/VVIP 등급별 혜택"""

INTENT_SYSTEM_PROMPT = """당신은 KT 고객센터 실시간 상담 지원 AI입니다.

## 역할
고객 발화를 분석하여 **핵심 의도**를 파악합니다.

## 작업 지시사항
1. 최근 대화를 기준으로 고객의 핵심 의도를 **한 가지**로 정리하세요
2. 여러 의도가 있을 경우 가장 중요한 것을 선택합니다
3. 의도 판단의 근거를 명확히 설명합니다

## 중요: 의도 판단 기준
- **반드시 고객의 실제 발화 내용**만을 기준으로 의도를 판단하세요
- 고객 프로필 정보(요금제, 등급 등)로 의도를 추측하지 마세요
- 감탄사, 인사말, 짧은 응답('아', '네', '음', '아아' 등)만 있는 경우:
  - intent_label: '의도 불명확'
  - intent_confidence: 0.1 이하
  - 고객의 구체적인 요청이 나올 때까지 기다리세요
- 고객이 명시적으로 요청이나 질문을 하지 않았다면 의도를 추측하지 마세요

## 출력 형식
- intent_label: 한글 라벨 (예: '요금제 변경', 'PASS 보안 문의', '의도 불명확')
- intent_confidence: 0~1 사이 확신도 (발화 내용이 불명확하면 0.1 이하)
- intent_explanation: 왜 그렇게 판단했는지 한두 문장으로 작성

## KT 서비스 관련 의도 예시
- 요금제 관련: 요금제 변경, 요금 조회, 요금제 추천
- 부가서비스: PASS 인증 문의, 스팸차단 설정, 로밍 신청
- 결합/멤버십: 결합할인 문의, 멤버십 혜택 확인
- 기술지원: 통화품질 불량, 데이터 속도 저하
- 보안: 명의도용 의심, 스미싱 문자 확인
- 불명확: 의도 불명확 (발화 내용이 부족하거나 명확하지 않은 경우)"""

# RAG 검색이 필요한 의도 키워드 (이 키워드가 포함된 의도일 때만 RAG tool 호출)
# rag_policy.py의 RAG_TRIGGERING_KEYWORDS와 동기화
RAG_TRIGGERING_KEYWORDS = [
    # 요금제/요금 관련
    "요금", "요금제", "청구", "고지", "플랜", "데이터", "무제한",
    # 결합/할인 관련
    "할인", "결합", "가족", "번들",
    # 위약금/해지/약정 관련
    "위약금", "해지", "약정", "계약",
    # 부가서비스 관련
    "로밍", "소액결제", "부가서비스",
    # TV/인터넷 관련
    "TV", "인터넷", "IPTV",
    # 멤버십 관련
    "멤버십", "VIP", "포인트", "혜택",
    # 명의변경
    "명의", "명의변경",
    # 기타
    "5G", "LTE",
]


# RAG 트리거 최소 신뢰도 임계값
RAG_CONFIDENCE_THRESHOLD = 0.5


def _should_trigger_rag(
    intent_label: str,
    customer_query: str,
    intent_confidence: float = 1.0
) -> bool:
    """의도와 쿼리를 분석하여 RAG 검색이 필요한지 판단합니다.

    Args:
        intent_label: 의도 라벨
        customer_query: 고객 발화 텍스트
        intent_confidence: 의도 신뢰도 (기본값 1.0)

    Returns:
        RAG 검색 필요 여부
    """
    # 의도가 불명확하거나 신뢰도가 낮으면 RAG 스킵
    if intent_label == "의도 불명확":
        return False

    if intent_confidence < RAG_CONFIDENCE_THRESHOLD:
        logger.info(
            f"_should_trigger_rag: 신뢰도 낮음 ({intent_confidence:.2f} < {RAG_CONFIDENCE_THRESHOLD}), RAG 스킵"
        )
        return False

    combined_text = f"{intent_label} {customer_query}".lower()

    for keyword in RAG_TRIGGERING_KEYWORDS:
        if keyword.lower() in combined_text:
            return True

    return False

SENTIMENT_SYSTEM_PROMPT = """당신은 KT 고객센터 실시간 상담 지원 AI입니다.

## 역할
고객의 발화를 분석하여 **감정 상태**를 파악합니다.

## 작업 지시사항
1. 최근 고객 발화에서 대표 감정을 파악합니다
2. 감정의 강도와 판단 근거를 제시합니다
3. 상담사가 고객 응대 시 참고할 수 있도록 분석합니다

## 출력 형식
- sentiment_label: 감정 라벨 ('불안', '혼란', '분노', '짜증', '안정', '만족', '무난')
- sentiment_score: 0~1 사이 감정 강도
- sentiment_explanation: 근거 한두 문장

## 감정 판단 기준
- 불안: 해킹, 개인정보 유출, 요금 폭탄 걱정
- 혼란: 서비스 이해 부족, 복잡한 안내에 대한 어려움
- 분노: 반복 문의, 서비스 불만, 불공정 처우
- 짜증: 대기시간, 절차 복잡, 해결 지연
- 안정/만족: 문제 해결, 명확한 안내 후"""

DRAFT_REPLY_SYSTEM_PROMPT = """당신은 KT 고객센터 실시간 상담 지원 AI입니다.

## 역할
상담사가 **바로 읽고 말할 수 있는** 응답 초안과 핵심 키워드를 생성합니다.

## 작업 지시사항
1. 현재 대화 맥락과 고객 감정을 고려한 짧은 응답을 작성합니다
2. 자연스러운 한국어 구어체로 작성합니다
3. 응답에 포함할 핵심 키워드를 추출합니다

## 출력 형식
- short_reply: 짧고 핵심만 단호하게 말하는 1-2문장
- keywords: 응답에 포함할 핵심 키워드 3-5개 (예: ["본인인증", "정상", "은행앱"])

## 응답 작성 원칙
- 고객 감정이 부정적일 때: 공감 표현 먼저, 그 다음 해결책
- 고객이 혼란스러울 때: 단계별로 명확하게 설명
- 보안 관련 문의: 안심시키는 표현 + 정확한 정보 제공
- 불만 상황: 사과 + 해결 방안 제시"""

RISK_SYSTEM_PROMPT = """당신은 KT 고객센터 실시간 상담 지원 AI입니다.

## 역할
대화에서 **잠재적 위험 요소**를 조기에 감지합니다.

## 작업 지시사항
1. 최근 대화에서 아래 위험 요소가 있는지 판단합니다
2. 해당되는 위험 코드만 리스트에 포함합니다
3. 위험 요소가 없으면 빈 리스트를 반환합니다

## 위험 플래그 (risk_flags)
- 'security_concern': 해킹/사기/개인정보 유출 의심
- 'cancellation_risk': 해지/타사 이동/강한 불만 표출
- 'refund_demand': 환불/보상 요구
- 'complaint_escalation': 민원/신고 언급, 상담에 대한 강한 불만

## 출력 형식
- risk_flags: 감지된 리스크 코드 리스트 (없으면 빈 리스트 [])
- risk_explanation: 왜 위험 요소로 판단했는지 한두 문장 (없으면 "위험 요소 없음")

## 판단 기준
- 명시적 언급: "해지할게요", "소보원에 신고", "환불해주세요"
- 암시적 신호: 반복적 불만, 감정 고조, 경쟁사 언급"""


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


# ---------- 공통 유틸 ----------
def _format_conversation_text(conversation_history: List[Dict[str, Any]]) -> str:
    """speaker: text 형식으로 문자열 변환."""
    lines = []
    for entry in conversation_history:
        speaker = entry.get("speaker_name", "Unknown")
        text = entry.get("text", "")
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def with_timing(
    node_name: str,
    node_fn: Callable[[Any, Runtime], Awaitable[Dict[str, Any]]]
) -> Callable[[Any, Runtime], Awaitable[Dict[str, Any]]]:
    """노드 실행 시간을 측정하고 결과에 메트릭을 포함시킵니다."""

    async def _wrapped(state: ConversationState, runtime: Runtime[ContextSchema]) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            result = await node_fn(state, runtime)
        except Exception:
            # 실패 시에도 시간 기록을 남기기 위해 다시 raise 전에 메트릭 기록
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(f"[{node_name}] node failed after {elapsed_ms} ms")
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        metrics = {
            "node": node_name,
            "elapsed_ms": elapsed_ms,
            "timestamp": int(time.time() * 1000),
        }
        logger.info(f"TIMING [{node_name}] {elapsed_ms}ms")

        if isinstance(result, dict):
            # 노드별 메트릭 필드를 포함시켜 stream_mode='updates'에서도 노드 이름과 함께 전달
            return {**result, f"{node_name}_metrics": metrics}
        return {f"{node_name}_metrics": metrics}

    return _wrapped


# ---------- 요약 노드----------
def create_summarize_node(llm: BaseChatModel):
    structured_llm = llm.with_structured_output(
        CONVERSATION_SUMMARY_SCHEMA,
        method="json_schema",
    )
    logger.info("JSON Schema 구조화 출력용 Structured LLM 생성 완료 (요약)")


    async def summarize_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        logger.info("summarize_node started (structured output mode)")
        conversation_history = state.get("conversation_history", [])
        last_summarized_index = state.get("last_summarized_index", 0)
        current_summary = state.get("current_summary", "")
        existing_summary_result = state.get("summary_result", {})

        total_count = len(conversation_history)
        if last_summarized_index >= total_count:
            logger.info("No new transcripts, returning existing summary")
            return {
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        new_entries = conversation_history[last_summarized_index:]
        new_last_index = total_count

        new_conversation_text = _format_conversation_text(new_entries)

        # 이전 요약 텍스트 구성
        previous_summary_text = "없음"
        try:
            if existing_summary_result:
                prev = SummaryResult(**existing_summary_result)
                previous_summary_text = (
                    f"- summary: {prev.summary}\n"
                    f"- customer_issue: {prev.customer_issue}\n"
                    f"- agent_action: {prev.agent_action}"
                )
        except Exception:
            previous_summary_text = "없음"

        # HumanMessage: 변수(데이터)만 전달
        user_content = f"""[이전 요약]
{previous_summary_text}

[새로 추가된 대화]
{new_conversation_text}"""

        # OpenAI Prompt Caching: 노드별 정적 시스템 프롬프트 + 고객 컨텍스트
        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{SUMMARIZE_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        logger.info("Calling structured LLM for summary...")
        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            latest_summary = SummaryResult(**result)
            summary_json = latest_summary.model_dump_json(ensure_ascii=False)
        except Exception as e:
            logger.error(f"Structured LLM call failed in summarize_node: {e}")
            return {
                "summary_result": state.get("summary_result", {}),
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        return {
            "summary_result": latest_summary.model_dump(),
            "current_summary": summary_json,
            "last_summarized_index": new_last_index
        }

    return summarize_node


# ---------- 의도파악 노드 ----------

def _has_customer_turn_since(
    conversation_history: List[Dict[str, Any]],
    last_index: int
) -> bool:
    """last_index 이후로 고객 발화가 있는지 확인합니다.

    고객 발화 판별 기준:
    - speaker_name이 '고객'으로 시작하거나
    - speaker_id가 'user' 또는 'customer'로 시작하거나
    - is_customer 플래그가 True인 경우
    """
    for entry in conversation_history[last_index:]:
        speaker_name = entry.get("speaker_name", "")
        speaker_id = entry.get("speaker_id", "")
        is_customer = entry.get("is_customer", False)

        if is_customer:
            return True
        if speaker_name.startswith("고객"):
            return True
        if speaker_id.startswith("user") or speaker_id.startswith("customer"):
            return True

    return False


def create_intent_node(llm: BaseChatModel):
    structured_llm = llm.with_structured_output(
        INTENT_SCHEMA,
        method="json_schema",
    )
    logger.info("JSON Schema 구조화 출력용 Structured LLM 생성 완료 (의도파악)")

    async def intent_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        last_intent_index = state.get("last_intent_index", 0)
        has_new_customer_turn = state.get("has_new_customer_turn", False)

        # has_new_customer_turn 플래그가 명시적으로 설정된 경우 사용
        # 그렇지 않으면 last_intent_index 이후 고객 발화 여부 확인
        if not has_new_customer_turn:
            has_new_customer_turn = _has_customer_turn_since(
                conversation_history, last_intent_index
            )

        # 고객 발화가 없으면 의도 분석 스킵
        if not has_new_customer_turn:
            logger.info("intent_node: 새로운 고객 발화 없음, 의도 분석 스킵")
            return {
                "last_intent_index": len(conversation_history)
            }

        # 직전 몇 턴만 사용 (예: 마지막 6개 정도)
        recent = conversation_history[-6:]
        convo_text = _format_conversation_text(recent)

        # HumanMessage: 변수(데이터)만 전달
        user_content = f"""[최근 대화]
{convo_text}"""

        # OpenAI Prompt Caching: 노드별 정적 시스템 프롬프트 + 고객 컨텍스트
        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{INTENT_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            return {
                "intent_result": result,
                "last_intent_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"intent_node LLM call failed: {e}")
            return {"last_intent_index": len(conversation_history)}

    return intent_node


# ---------- 감정분석 노드 ----------

def create_sentiment_node(llm: BaseChatModel):
    structured_llm = llm.with_structured_output(
        SENTIMENT_SCHEMA,
        method="json_schema",
    )
    logger.info("JSON Schema 구조화 출력용 Structured LLM 생성 완료 (감정분석)")

    async def sentiment_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        # 고객 발화가 없으면 감정 분석 스킵
        last_sentiment_index = state.get("last_sentiment_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_sentiment_index
        )

        if not has_new_customer_turn:
            logger.info("sentiment_node: 새로운 고객 발화 없음, 감정 분석 스킵")
            return {"last_sentiment_index": len(conversation_history)}

        # 고객 발화 위주로 직전 몇 개 사용
        recent_user_utts = [
            e for e in conversation_history[-8:]
            if e.get("speaker_name", "").startswith("고객") or e.get("speaker_id", "").startswith("user")
        ] or conversation_history[-4:]

        convo_text = _format_conversation_text(recent_user_utts)

        # HumanMessage: 변수(데이터)만 전달
        user_content = f"""[최근 고객 발화]
{convo_text}"""

        # OpenAI Prompt Caching: 노드별 정적 시스템 프롬프트 + 고객 컨텍스트
        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{SENTIMENT_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            return {
                "sentiment_result": result,
                "last_sentiment_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"sentiment_node LLM call failed: {e}")
            return {"last_sentiment_index": len(conversation_history)}

    return sentiment_node


# ---------- 응답 초안 추천 노드 ----------

def create_draft_reply_node(llm: BaseChatModel):
    structured_llm = llm.with_structured_output(
        DRAFT_REPLY_SCHEMA,
        method="json_schema",
    )
    logger.info("JSON Schema 구조화 출력용 Structured LLM 생성 완료 (응답 초안 추천)")

    async def draft_reply_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        # 고객 발화가 없으면 응답 초안 생성 스킵
        last_draft_index = state.get("last_draft_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_draft_index
        )

        if not has_new_customer_turn:
            logger.info("draft_reply_node: 새로운 고객 발화 없음, 응답 초안 생성 스킵")
            return {"last_draft_index": len(conversation_history)}

        recent = conversation_history[-8:]
        convo_text = _format_conversation_text(recent)

        intent = state.get("intent_result") or {}
        sentiment = state.get("sentiment_result") or {}

        # HumanMessage: 변수(데이터)만 전달
        user_content = f"""[최근 대화]
{convo_text}

[현재 인식된 의도]
{intent}

[현재 인식된 감정]
{sentiment}"""

        # OpenAI Prompt Caching: 노드별 정적 시스템 프롬프트 + 고객 컨텍스트
        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{DRAFT_REPLY_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            return {
                "draft_replies": result,
                "last_draft_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"draft_reply_node LLM call failed: {e}")
            return {"last_draft_index": len(conversation_history)}

    return draft_reply_node


# ---------- 위험 대응 경고 노드 ----------

def create_risk_node(llm: BaseChatModel):
    structured_llm = llm.with_structured_output(
        RISK_SCHEMA,
        method="json_schema",
    )
    logger.info("JSON Schema 구조화 출력용 Structured LLM 생성 완료 (위험 대응 경고)")

    async def risk_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        # 고객 발화가 없으면 위험 감지 스킵
        last_risk_index = state.get("last_risk_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_risk_index
        )

        if not has_new_customer_turn:
            logger.info("risk_node: 새로운 고객 발화 없음, 위험 감지 스킵")
            return {"last_risk_index": len(conversation_history)}

        recent = conversation_history[-12:]
        convo_text = _format_conversation_text(recent)

        # HumanMessage: 변수(데이터)만 전달
        user_content = f"""[최근 대화]
{convo_text}"""

        # OpenAI Prompt Caching: 노드별 정적 시스템 프롬프트 + 고객 컨텍스트
        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{RISK_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result: Dict[str, Any] = await structured_llm.ainvoke(messages)
            return {
                "risk_result": result,
                "last_risk_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"risk_node LLM call failed: {e}")
            return {"last_risk_index": len(conversation_history)}

    return risk_node


# ---------- RAG 정책 검색 노드 생성 (기존 방식) ----------

def create_rag_policy_node():
    """RAG 정책 검색 노드를 생성합니다.

    intent 노드 이후 실행되며, intent_result를 기반으로 RAG 검색을 수행합니다.
    """
    from modules.agent.tools.rag_policy import rag_policy_search

    async def rag_policy_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        """의도 기반 RAG 정책 검색 노드.

        intent_result의 intent_label을 사용하여 관련 정책을 검색합니다.
        고객 정보(customer_info)를 활용하여 맞춤형 추천을 제공합니다.
        """
        conversation_history = state.get("conversation_history", [])
        intent_result = state.get("intent_result", {})
        customer_info = state.get("customer_info", {})
        last_rag_index = state.get("last_rag_index", 0)

        # 의도 분석 결과가 없으면 스킵
        if not intent_result:
            logger.info("rag_policy_node: no intent_result, skipping")
            return {"last_rag_index": len(conversation_history)}

        intent_label = intent_result.get("intent_label", "")
        intent_confidence = intent_result.get("intent_confidence", 0.0)

        # 최근 고객 발화 추출
        recent_customer_utts = []
        for entry in reversed(conversation_history[-6:]):
            speaker_name = entry.get("speaker_name", "")
            is_customer = entry.get("is_customer", False)
            if is_customer or speaker_name.startswith("고객"):
                recent_customer_utts.insert(0, entry.get("text", ""))
                if len(recent_customer_utts) >= 2:
                    break
        customer_query = " ".join(recent_customer_utts)

        # RAG 트리거 여부 확인 (신뢰도도 함께 전달)
        if not _should_trigger_rag(intent_label, customer_query, intent_confidence):
            logger.info(f"rag_policy_node: RAG not needed for intent='{intent_label}' (confidence={intent_confidence:.2f})")
            return {
                "rag_policy_result": {
                    "skipped": True,
                    "skip_reason": "RAG 검색이 필요하지 않은 의도입니다.",
                    "intent_label": intent_label
                },
                "last_rag_index": len(conversation_history)
            }

        logger.info(f"rag_policy_node: searching for intent='{intent_label}'")

        try:
            rag_result = await rag_policy_search(
                intent_label=intent_label,
                customer_query=customer_query,
                customer_info=customer_info,
                top_k=5
            )
            result_dict = rag_result.to_dict()
            result_dict["skipped"] = False

            logger.info(f"rag_policy_node: found {len(rag_result.recommendations)} recommendations")

            return {
                "rag_policy_result": result_dict,
                "last_rag_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"rag_policy_node search failed: {e}")
            return {
                "rag_policy_result": {
                    "skipped": False,
                    "intent_label": intent_label,
                    "query": customer_query,
                    "searched_classifications": [],
                    "recommendations": [],
                    "search_context": "",
                    "error": str(e)
                },
                "last_rag_index": len(conversation_history)
            }

    return rag_policy_node


# ---------- FAQ Semantic Cache 검색 노드 ----------

# FAQ 카테고리 매핑 (의도 -> FAQ 카테고리)
FAQ_INTENT_CATEGORY_MAP = {
    "멤버십 문의": "멤버십 혜택",
    "VIP 문의": "등급",
    "VVIP 문의": "등급",
    "등급 문의": "등급",
    "포인트 문의": "등급",
    "혜택 문의": "멤버십 혜택",
    "영화 할인": "멤버십 혜택",
    "제휴 할인": "멤버십 혜택",
    "카드 발급": "가입/카드발급",
    "멤버십 가입": "가입/카드발급",
}

# FAQ 검색 트리거 키워드
FAQ_TRIGGERING_KEYWORDS = [
    "멤버십", "VIP", "VVIP", "포인트", "혜택", "등급",
    "영화", "할인", "스타벅스", "커피", "제휴",
    "카드", "발급", "가입",
]


def _should_trigger_faq(intent_label: str, customer_query: str) -> tuple[bool, str | None]:
    """FAQ 검색이 필요한지 판단하고 카테고리를 반환합니다.

    Returns:
        (should_search, category): 검색 여부와 FAQ 카테고리
    """
    # 의도 기반 카테고리 매핑
    for intent_key, category in FAQ_INTENT_CATEGORY_MAP.items():
        if intent_key in intent_label:
            return True, category

    # 키워드 기반 감지
    combined_text = f"{intent_label} {customer_query}".lower()
    for keyword in FAQ_TRIGGERING_KEYWORDS:
        if keyword.lower() in combined_text:
            # 키워드로 카테고리 추정
            if any(k in combined_text for k in ["vip", "vvip", "등급", "포인트"]):
                return True, "등급"
            elif any(k in combined_text for k in ["영화", "할인", "스타벅스", "혜택", "제휴"]):
                return True, "멤버십 혜택"
            elif any(k in combined_text for k in ["카드", "발급", "가입"]):
                return True, "가입/카드발급"
            return True, None  # 카테고리 미지정

    return False, None


def create_faq_search_node():
    """FAQ Semantic Cache 검색 노드를 생성합니다.

    intent 노드 이후 rag_policy와 병렬로 실행되며,
    의도 기반으로 FAQ semantic cache를 검색합니다.
    """
    from modules.database import get_faq_service

    async def faq_search_node(
        state: ConversationState,
        runtime: Runtime[ContextSchema]
    ) -> Dict[str, Any]:
        """FAQ semantic cache 검색 노드.

        intent_result를 기반으로 FAQ를 검색합니다.
        rag_policy와 병렬로 실행되어 빠른 응답을 제공합니다.
        """
        conversation_history = state.get("conversation_history", [])
        intent_result = state.get("intent_result", {})
        last_faq_index = state.get("last_faq_index", 0)

        # 의도 분석 결과가 없으면 스킵
        if not intent_result:
            logger.info("faq_search_node: no intent_result, skipping")
            return {"last_faq_index": len(conversation_history)}

        intent_label = intent_result.get("intent_label", "")

        # 최근 고객 발화 추출
        recent_customer_utts = []
        for entry in reversed(conversation_history[-6:]):
            speaker_name = entry.get("speaker_name", "")
            is_customer = entry.get("is_customer", False)
            if is_customer or speaker_name.startswith("고객"):
                recent_customer_utts.insert(0, entry.get("text", ""))
                if len(recent_customer_utts) >= 2:
                    break
        customer_query = " ".join(recent_customer_utts)

        # FAQ 트리거 여부 및 카테고리 확인
        should_search, category = _should_trigger_faq(intent_label, customer_query)

        if not should_search:
            logger.info(f"faq_search_node: FAQ not needed for intent='{intent_label}'")
            return {
                "faq_result": {
                    "skipped": True,
                    "skip_reason": "FAQ 검색이 필요하지 않은 의도입니다.",
                    "intent_label": intent_label
                },
                "last_faq_index": len(conversation_history)
            }

        logger.info(f"faq_search_node: searching FAQ for intent='{intent_label}', category='{category}'")

        try:
            faq_service = get_faq_service()
            if not faq_service.is_initialized:
                await faq_service.initialize()

            # Semantic cache 검색
            result = await faq_service.semantic_search(
                query=customer_query,
                category=category,
                limit=3,
                use_cache=True,
                distance_threshold=0.45,
            )

            faq_result = {
                "skipped": False,
                "intent_label": intent_label,
                "query": customer_query,
                "category": category,
                "cache_hit": result.cache_hit,
                "similarity_score": result.similarity_score,
                "cached_query": result.cached_query,
                "search_time_ms": result.search_time_ms,
                "faqs": result.faqs,
            }

            logger.info(
                f"faq_search_node: found {len(result.faqs)} FAQs "
                f"(cache_hit={result.cache_hit}, similarity={result.similarity_score:.3f})"
            )

            return {
                "faq_result": faq_result,
                "last_faq_index": len(conversation_history)
            }

        except Exception as e:
            logger.error(f"faq_search_node search failed: {e}")
            return {
                "faq_result": {
                    "skipped": False,
                    "intent_label": intent_label,
                    "query": customer_query,
                    "category": category,
                    "faqs": [],
                    "error": str(e)
                },
                "last_faq_index": len(conversation_history)
            }

    return faq_search_node


# ---------- 그래프 생성 ----------
def create_agent_graph(llm: BaseChatModel) -> StateGraph:
    """실시간 상담 지원 에이전트 그래프 생성.

    그래프 구조:
        START
          |
          +---> summarize ---------> END
          |
          +---> intent --+-> rag_policy ---> END  (정책 RAG 검색)
          |              |
          |              +-> faq_search ----> END  (FAQ semantic cache - 병렬)
          |
          +---> sentiment ---------> END
          |
          +---> draft_reply -------> END
          |
          +---> risk --------------> END

    듀얼 패스 RAG 검색:
        - intent 노드에서 의도 분석 후 병렬 분기
        - rag_policy: 정책 RAG 검색 (요금제, 결합할인 등)
        - faq_search: FAQ semantic cache 검색 (멤버십 FAQ)
        - 두 결과를 프론트엔드에서 통합하여 RAG 카드에 표시
    """

    graph = StateGraph(
        ConversationState,
        context_schema=ContextSchema
    )

    # 노드 생성
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

    # START에서 다섯 노드로 "팬아웃" (rag_policy, faq_search 제외)
    graph.add_edge(START, "summarize")
    graph.add_edge(START, "intent")
    graph.add_edge(START, "sentiment")
    graph.add_edge(START, "draft_reply")
    graph.add_edge(START, "risk")

    # intent -> rag_policy, faq_search (의도 분석 후 병렬 RAG 검색)
    graph.add_edge("intent", "rag_policy")
    graph.add_edge("intent", "faq_search")

    # 각 노드에서 END로 "팬인"
    graph.add_edge("summarize", END)
    graph.add_edge("sentiment", END)
    graph.add_edge("draft_reply", END)
    graph.add_edge("risk", END)
    graph.add_edge("rag_policy", END)
    graph.add_edge("faq_search", END)

    compiled_graph = graph.compile()
    logger.info("상담 지원 그래프 생성 완료 (intent -> rag_policy/faq_search 병렬 실행)")
    return compiled_graph
