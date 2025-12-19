"""LangGraph 노드 정의 모듈.

각 노드는 ConversationState를 받아 특정 분석을 수행하고 결과를 반환합니다.
- summarize: 대화 요약
- intent: 의도 분석
- sentiment: 감정 분석
- draft_reply: 응답 초안 생성
- risk: 위험 감지
- rag_policy: RAG 정책 검색
- faq_search: FAQ 검색
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass, field

from langgraph.runtime import Runtime
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from .schemas import (
    SummaryResult,
    IntentResult,
    SentimentResult,
    DraftReplyResult,
    RiskResult,
)
from .prompts import (
    SUMMARIZE_SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    SENTIMENT_SYSTEM_PROMPT,
    DRAFT_REPLY_SYSTEM_PROMPT,
    RISK_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# =============================================================================
# RAG 정책 관련 상수 및 데이터 구조 (rag_policy.py 통합)
# =============================================================================

# 실제 컬렉션 및 분류 정보
# 컬렉션 목록 (langchain_pg_embedding, 1536차원, text-embedding-3-small)
EMBEDDING_TABLE = "langchain_pg_embedding"

# 컬렉션 이름 목록
COLLECTIONS = {
    "mobile": "kt_mobile_plans",
    "internet": "kt_internet_plans",
    "tv": "kt_tv_plans",
    "bundle": "kt_bundle_discount",
    "penalty": "kt_mobile_penalty",
    "membership": "kt_membership",
}

# RAG 검색이 필요한 의도 키워드
RAG_TRIGGERING_KEYWORDS = [
    "요금", "요금제", "청구", "고지", "플랜", "데이터", "무제한",
    "할인", "결합", "가족", "번들",
    "위약금", "해지", "약정", "계약",
    "로밍", "소액결제", "부가서비스",
    "TV", "인터넷", "IPTV",
    "멤버십", "VIP", "포인트", "혜택",
    "명의", "명의변경",
    "5G", "LTE",
]

# RAG 트리거 최소 신뢰도 임계값
RAG_CONFIDENCE_THRESHOLD = 0.5

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

# 의도 -> 컬렉션 매핑
INTENT_COLLECTION_MAP: Dict[str, List[str]] = {
    "요금 조회": ["mobile"],
    "요금제 변경": ["mobile"],
    "요금제 추천": ["mobile"],
    "요금 고지 문자 해석 요청": ["mobile"],
    "청구서 문의": ["mobile"],
    "데이터 초과 요금": ["mobile"],
    "결합할인 문의": ["bundle", "internet", "tv"],
    "가족결합 문의": ["bundle"],
    "인터넷 결합": ["bundle", "internet"],
    "TV 결합": ["bundle", "tv"],
    "5G 요금제": ["mobile"],
    "LTE 요금제": ["mobile"],
    "인터넷 요금제": ["internet"],
    "TV 서비스": ["tv"],
    "위약금 문의": ["penalty"],
    "해지 문의": ["penalty"],
    "약정 문의": ["penalty"],
    "멤버십 문의": ["membership"],
    "포인트 문의": ["membership"],
    "default": ["mobile", "bundle"],
}

# 키워드 기반 컬렉션 매칭
KEYWORD_COLLECTION_MAP: Dict[str, List[str]] = {
    "요금": ["mobile"],
    "요금제": ["mobile"],
    "할인": ["bundle"],
    "결합": ["bundle"],
    "인터넷": ["internet", "bundle"],
    "TV": ["tv", "bundle"],
    "5G": ["mobile"],
    "LTE": ["mobile"],
    "데이터": ["mobile"],
    "무제한": ["mobile"],
    "위약금": ["penalty"],
    "해지": ["penalty"],
    "약정": ["penalty"],
    "멤버십": ["membership"],
    "VIP": ["membership"],
    "포인트": ["membership"],
}


# =============================================================================
# RAG 정책 관련 데이터 클래스
# =============================================================================

@dataclass
class CustomerContext:
    """고객 컨텍스트 정보."""
    customer_name: str = ""
    current_plan: str = ""
    monthly_fee: int = 0
    membership_grade: str = ""
    contract_status: str = ""
    bundle_info: str = ""
    age: int = 0
    current_data_gb: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomerContext":
        if not data:
            return cls()
        return cls(
            customer_name=data.get("customer_name", ""),
            current_plan=data.get("current_plan", ""),
            monthly_fee=data.get("monthly_fee", 0),
            membership_grade=data.get("membership_grade", ""),
            contract_status=data.get("contract_status", ""),
            bundle_info=data.get("bundle_info", ""),
            age=data.get("age", 0),
            current_data_gb=data.get("current_data_gb", 0),
        )

    def get_customer_segments(self) -> List[str]:
        """고객 특성을 기반으로 타겟 세그먼트 키워드를 추출합니다."""
        segments = []
        if self.age > 0:
            if self.age <= 18:
                segments.extend(["청소년", "학생", "Y틴", "틴"])
            elif self.age <= 34:
                segments.extend(["MZ세대", "청년", "Y", "젊은"])
            elif self.age <= 50:
                segments.extend(["중장년", "직장인", "프리미엄"])
            elif self.age <= 64:
                segments.extend(["중장년", "시니어"])
            else:
                segments.extend(["시니어", "어르신", "효도", "65세"])
        if self.membership_grade:
            grade = self.membership_grade.upper()
            if grade in ["VVIP", "VIP"]:
                segments.extend(["프리미엄", "헤비유저", "고객"])
            elif grade == "GENERAL":
                segments.extend(["가성비", "저사용자"])
        if self.monthly_fee > 0:
            if self.monthly_fee >= 60000:
                segments.extend(["프리미엄", "헤비유저"])
            elif self.monthly_fee >= 40000:
                segments.extend(["가성비", "중간"])
            else:
                segments.extend(["저가", "저사용자", "가성비"])
        return segments


@dataclass
class PolicyRecommendation:
    """단일 정책/문구 추천 결과."""
    collection: str
    title: str
    content: str
    relevance_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    recommendation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collection": self.collection,
            "title": self.title,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
            "recommendation_reason": self.recommendation_reason,
        }


@dataclass
class RAGPolicyResult:
    """RAG 정책 검색 전체 결과."""
    intent_label: str
    query: str
    searched_classifications: List[str]
    recommendations: List[PolicyRecommendation]
    search_context: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_label": self.intent_label,
            "query": self.query,
            "searched_classifications": self.searched_classifications,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "search_context": self.search_context,
            "error": self.error,
        }


# =============================================================================
# 공통 유틸 함수
# =============================================================================

def _format_conversation_text(conversation_history: List[Dict[str, Any]]) -> str:
    """speaker: text 형식으로 문자열 변환."""
    lines = []
    for entry in conversation_history:
        speaker = entry.get("speaker_name", "Unknown")
        text = entry.get("text", "")
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _has_customer_turn_since(
    conversation_history: List[Dict[str, Any]],
    last_index: int
) -> bool:
    """last_index 이후로 고객 발화가 있는지 확인합니다."""
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


def _should_trigger_rag(
    intent_label: str,
    customer_query: str,
    intent_confidence: float = 1.0
) -> bool:
    """의도와 쿼리를 분석하여 RAG 검색이 필요한지 판단합니다."""
    if intent_label == "의도 불명확":
        return False
    if intent_confidence < RAG_CONFIDENCE_THRESHOLD:
        logger.info(
            f"[RAG] 신뢰도 낮음 ({intent_confidence:.2f} < {RAG_CONFIDENCE_THRESHOLD}), RAG 스킵"
        )
        return False
    combined_text = f"{intent_label} {customer_query}".lower()
    for keyword in RAG_TRIGGERING_KEYWORDS:
        if keyword.lower() in combined_text:
            return True
    return False


def _is_similar_query(query1: str, query2: str, threshold: float = 0.7) -> bool:
    """두 쿼리가 유사한지 간단히 비교합니다 (키워드 기반)."""
    if not query1 or not query2:
        return False
    words1 = set(w for w in query1.lower().split() if len(w) >= 2)
    words2 = set(w for w in query2.lower().split() if len(w) >= 2)
    if not words1 or not words2:
        return query1.strip() == query2.strip()
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return (intersection / union) >= threshold if union > 0 else False


def _should_trigger_faq_by_text(customer_query: str) -> bool:
    """고객 발화 텍스트만으로 FAQ 검색이 필요한지 판단합니다."""
    if not customer_query or len(customer_query.strip()) < 3:
        return False
    query_lower = customer_query.lower()
    for keyword in FAQ_TRIGGERING_KEYWORDS:
        if keyword.lower() in query_lower:
            return True
    return False


def with_timing(
    node_name: str,
    node_fn: Callable[[Any, Any], Awaitable[Dict[str, Any]]]
) -> Callable[[Any, Any], Awaitable[Dict[str, Any]]]:
    """노드 실행 시간을 측정하고 결과에 메트릭을 포함시킵니다."""

    async def _wrapped(state: Any, runtime: Any) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            result = await node_fn(state, runtime)
        except Exception:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(f"[에이전트] {node_name} 노드 실패: {elapsed_ms}ms")
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        metrics = {
            "node": node_name,
            "elapsed_ms": elapsed_ms,
            "timestamp": int(time.time() * 1000),
        }
        logger.debug(f"[에이전트] {node_name} 실행: {elapsed_ms}ms")

        if isinstance(result, dict):
            return {**result, f"{node_name}_metrics": metrics}
        return {f"{node_name}_metrics": metrics}

    return _wrapped


# =============================================================================
# RAG 정책 검색 내부 함수 (rag_policy.py 통합)
# =============================================================================

def _get_collections_for_intent(intent_label: str, query: str) -> List[str]:
    """의도와 쿼리를 분석하여 검색할 컬렉션 목록을 반환합니다."""
    collection_keys = set()
    if intent_label in INTENT_COLLECTION_MAP:
        collection_keys.update(INTENT_COLLECTION_MAP[intent_label])
    for keyword, cols in KEYWORD_COLLECTION_MAP.items():
        if keyword in intent_label:
            collection_keys.update(cols)
    for keyword, cols in KEYWORD_COLLECTION_MAP.items():
        if keyword in query:
            collection_keys.update(cols)
    if not collection_keys:
        collection_keys.update(INTENT_COLLECTION_MAP["default"])
    collection_names = [COLLECTIONS[key] for key in collection_keys if key in COLLECTIONS]
    return collection_names


def _generate_recommendation_reason(
    rec: PolicyRecommendation,
    customer: CustomerContext,
    intent_label: str
) -> str:
    """고객 상황을 기반으로 추천 이유를 생성합니다."""
    reasons = []
    monthly_price = rec.metadata.get("monthly_price", 0)
    if monthly_price and customer.monthly_fee > 0:
        if monthly_price < customer.monthly_fee:
            diff = customer.monthly_fee - monthly_price
            reasons.append(f"현재 요금({customer.monthly_fee:,}원) 대비 월 {diff:,}원 절감 가능")
        elif monthly_price == customer.monthly_fee:
            reasons.append("현재 요금과 동일한 가격대")
    target_segment = rec.metadata.get("target_segment", "")
    if target_segment:
        if customer.membership_grade and customer.membership_grade in target_segment:
            reasons.append(f"{customer.membership_grade} 고객 대상 상품")
        elif "프리미엄" in target_segment and customer.membership_grade in ["VIP", "VVIP"]:
            reasons.append("프리미엄 고객 대상 상품")
        elif "가성비" in target_segment:
            reasons.append("가성비 추구 고객 추천")
    if "결합" in intent_label or rec.collection == "kt_bundle_discount":
        if customer.bundle_info:
            if "없음" in customer.bundle_info or "단독" in customer.bundle_info:
                reasons.append("현재 결합 미가입, 결합 시 추가 할인 가능")
            else:
                reasons.append("기존 결합 상품과 연계 가능")
    if "약정" in intent_label or "위약금" in intent_label or rec.collection == "kt_mobile_penalty":
        if "무약정" in customer.contract_status:
            reasons.append("무약정 상태로 요금제 변경 자유로움")
        elif "약정" in customer.contract_status:
            reasons.append("현재 약정 상태 확인 필요")
    return " / ".join(reasons) if reasons else "고객 문의 내용과 관련된 정보"


def _parse_data_amount_from_text(search_text: str) -> int:
    """search_text에서 데이터량(GB)을 파싱합니다."""
    import re
    if not search_text:
        return 0
    text_lower = search_text.lower()
    if "무제한" in text_lower or "unlimited" in text_lower:
        return 9999
    match = re.search(r'(\d+)\s*(?:gb|기가)', text_lower)
    if match:
        return int(match.group(1))
    return 0


def _calculate_segment_match_score(
    target_segment: str,
    price_sensitivity: str,
    customer_segments: List[str]
) -> int:
    """고객 세그먼트와 요금제 타겟 세그먼트의 매칭 점수를 계산합니다."""
    if not customer_segments:
        return 0
    combined_target = f"{target_segment} {price_sensitivity}".lower()
    match_count = 0
    for segment in customer_segments:
        if segment.lower() in combined_target:
            match_count += 1
    return match_count


def _sort_by_customer_fit(
    results: List[PolicyRecommendation],
    customer: CustomerContext
) -> List[PolicyRecommendation]:
    """고객 특성에 맞는 요금제 순으로 정렬합니다."""
    customer_segments = customer.get_customer_segments()
    current_fee = customer.monthly_fee
    current_data = customer.current_data_gb

    def calculate_sort_key(rec: PolicyRecommendation) -> tuple:
        search_text = rec.metadata.get("search_text", "")
        plan_data = _parse_data_amount_from_text(search_text)
        if current_data > 0 and plan_data > 0:
            if plan_data >= current_data:
                data_score = 0 if plan_data == 9999 else 1
            else:
                data_score = 3
        elif plan_data == 9999:
            data_score = 0
        else:
            data_score = 2
        target_segment = rec.metadata.get("target_segment", "")
        price_sensitivity = rec.metadata.get("price_sensitivity", "")
        segment_score = -_calculate_segment_match_score(
            target_segment, price_sensitivity, customer_segments
        )
        price = rec.metadata.get("monthly_price", 0) or 0
        if current_fee > 0 and price > 0:
            ratio = price / current_fee
            if 0.5 <= ratio <= 1.5:
                price_score = 0
            elif ratio < 0.5:
                price_score = 1
            else:
                price_score = 2
        else:
            price_score = 1
        similarity_score = -(rec.relevance_score or 0)
        return (data_score, segment_score, price_score, similarity_score)

    return sorted(results, key=calculate_sort_key)


async def _get_embedding(text: str) -> List[float]:
    """텍스트의 임베딩 벡터를 생성합니다."""
    from langchain_openai import OpenAIEmbeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vector = await embeddings.aembed_query(text)
    return vector


async def _search_with_collections(
    query_embedding: List[float],
    collection_names: List[str],
    customer: CustomerContext,
    intent_label: str,
    top_k: int = 5,
) -> List[PolicyRecommendation]:
    """컬렉션 필터를 적용하여 벡터 검색을 수행합니다."""
    from modules.database import get_db_manager
    import json
    import re

    try:
        db = get_db_manager()
        if not db.is_initialized:
            logger.warning("[RAG] DB 초기화 안됨, 검색 스킵")
            return []

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        if collection_names:
            collection_filter = " OR ".join([
                f"c.name = '{col}'" for col in collection_names
            ])
            where_clause = f"({collection_filter})"
        else:
            where_clause = "c.name = 'kt_mobile_plans'"

        if customer.current_plan:
            safe_plan_name = customer.current_plan.replace("'", "''")
            where_clause += f" AND (e.cmetadata->>'name' IS NULL OR e.cmetadata->>'name' != '{safe_plan_name}')"

        plan_collections = {"kt_mobile_plans", "kt_internet_plans", "kt_tv_plans"}
        is_plan_search = bool(set(collection_names) & plan_collections) if collection_names else True

        query = f"""
            SELECT
                c.name as collection_name,
                e.document,
                e.cmetadata,
                1 - (e.embedding <=> $1::vector) as similarity
            FROM {EMBEDDING_TABLE} e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE {where_clause}
            ORDER BY e.embedding <=> $1::vector
            LIMIT $2
        """

        rows = await db.fetch(query, embedding_str, top_k * 2)

        results = []
        for row in rows:
            metadata = row["cmetadata"] or {}
            title = metadata.get("name", "정책 문서")
            monthly_price = metadata.get("monthly_price_numeric", 0)

            plan_details = {}
            document_raw = row["document"]
            if document_raw:
                try:
                    json_match = re.search(r'상세 정보:\s*(\{.*\})\s*$', document_raw, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        doc_data = json.loads(json_str)
                        if isinstance(doc_data, dict):
                            plan_details = doc_data.get("plan_details", {})
                            if not title or title == "정책 문서":
                                title = doc_data.get("name", title)
                            if not monthly_price:
                                monthly_price = doc_data.get("monthly_price_numeric", 0)
                    else:
                        doc_data = json.loads(document_raw)
                        if isinstance(doc_data, dict):
                            plan_details = doc_data.get("plan_details", {})
                            if not title or title == "정책 문서":
                                title = doc_data.get("name", title)
                            if not monthly_price:
                                monthly_price = doc_data.get("monthly_price_numeric", 0)
                except (json.JSONDecodeError, TypeError):
                    pass

            rec = PolicyRecommendation(
                collection=row["collection_name"],
                title=title,
                content=document_raw[:500] if document_raw else "",
                relevance_score=float(row["similarity"]),
                metadata={
                    "monthly_price": monthly_price,
                    "target_segment": metadata.get("target_segment", ""),
                    "price_sensitivity": metadata.get("price_sensitivity", ""),
                    "product_type": metadata.get("product_type", ""),
                    "search_text": metadata.get("search_text", ""),
                    "plan_details": plan_details,
                },
            )
            rec.recommendation_reason = _generate_recommendation_reason(rec, customer, intent_label)
            results.append(rec)

        if is_plan_search:
            results = _sort_by_customer_fit(results, customer)

        return results[:top_k]

    except Exception as e:
        logger.error(f"[RAG] 검색 실패: {e}")
        return []


async def _get_all_membership_grades() -> List[PolicyRecommendation]:
    """모든 멤버십 등급 정보를 등급 순서대로 가져옵니다."""
    from modules.database import get_db_manager

    try:
        db = get_db_manager()
        if not db.is_initialized:
            return []

        query = """
            SELECT e.document, e.cmetadata
            FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = 'kt_membership'
            AND e.cmetadata->>'product_type' = 'membership'
            ORDER BY (e.cmetadata->>'grade_rank')::int
        """
        rows = await db.fetch(query)

        results = []
        for row in rows:
            metadata = row["cmetadata"] or {}
            grade = metadata.get("grade", "")
            spending = metadata.get("annual_spending", "")
            choice_count = metadata.get("choice_count", 0)
            benefits = metadata.get("key_benefits", "")

            rec = PolicyRecommendation(
                collection="kt_membership",
                title=f"KT 멤버십 {grade}",
                content=row["document"][:500],
                relevance_score=1.0,
                metadata={
                    "grade": grade,
                    "grade_rank": metadata.get("grade_rank", 99),
                    "annual_spending": spending,
                    "choice_count": choice_count,
                    "key_benefits": benefits,
                    "product_type": "membership",
                },
            )
            rec.recommendation_reason = f"{grade} 등급: 연 {spending} 이용 시 적용"
            results.append(rec)

        return results
    except Exception as e:
        logger.error(f"[RAG] 멤버십 등급 조회 실패: {e}")
        return []


def _format_membership_table(grades: List[PolicyRecommendation]) -> str:
    """멤버십 등급 정보를 표 형태의 문자열로 포맷합니다."""
    if not grades:
        return ""
    lines = [
        "[ KT 멤버십 등급 기준표 ]",
        "-" * 60,
        f"{'등급':<8} | {'연간 이용금액':<20} | {'초이스 혜택':<12}",
        "-" * 60,
    ]
    for rec in grades:
        meta = rec.metadata
        grade = meta.get("grade", "")
        spending = meta.get("annual_spending", "")
        choice = meta.get("choice_count", 0)
        choice_str = f"연 {choice}회" if choice > 0 else "없음"
        lines.append(f"{grade:<8} | {spending:<20} | {choice_str:<12}")
    lines.append("-" * 60)
    return "\n".join(lines)


def _generate_search_context(
    customer: CustomerContext,
    intent_label: str,
    collection_names: List[str]
) -> str:
    """검색 컨텍스트 설명을 생성합니다."""
    parts = []
    if customer.customer_name:
        parts.append(f"고객: {customer.customer_name}")
    if customer.current_plan:
        parts.append(f"현재 요금제: {customer.current_plan}")
    if customer.monthly_fee > 0:
        parts.append(f"월 요금: {customer.monthly_fee:,}원")
    if customer.membership_grade:
        parts.append(f"등급: {customer.membership_grade}")
    if customer.bundle_info and customer.bundle_info != "없음 (단독 회선)":
        parts.append(f"결합: {customer.bundle_info}")
    if collection_names:
        parts.append(f"검색 컬렉션: {', '.join(collection_names)}")
    return " | ".join(parts) if parts else "일반 검색"


async def rag_policy_search(
    intent_label: str,
    customer_query: str,
    customer_info: Optional[Dict[str, Any]] = None,
    conversation_context: str = "",
    top_k: int = 5,
) -> RAGPolicyResult:
    """고객 의도 기반 RAG 정책 검색을 수행합니다."""
    try:
        customer = CustomerContext.from_dict(customer_info or {})
        collection_names = _get_collections_for_intent(intent_label, customer_query)
        logger.info(
            f"[RAG] 검색 시작: 의도='{intent_label}', "
            f"컬렉션={collection_names}, 월요금={customer.monthly_fee}"
        )

        is_membership_grade_query = (
            "membership" in collection_names and
            any(kw in f"{intent_label} {customer_query}".lower()
                for kw in ["등급", "기준", "조건", "vvip", "vip", "gold", "silver"])
        )

        if is_membership_grade_query:
            all_grades = await _get_all_membership_grades()
            if all_grades:
                grade_table = _format_membership_table(all_grades)
                search_context = _generate_search_context(customer, intent_label, collection_names)
                search_context = f"{search_context}\n\n{grade_table}"
                return RAGPolicyResult(
                    intent_label=intent_label,
                    query=customer_query,
                    searched_classifications=collection_names,
                    recommendations=all_grades,
                    search_context=search_context,
                )

        search_query = f"{intent_label} {customer_query}"
        if customer.current_plan:
            search_query = f"{search_query} 현재 {customer.current_plan}"

        data_keywords = ["많은", "더", "늘리", "부족", "초과", "무제한", "대용량"]
        query_lower = customer_query.lower()
        if any(kw in query_lower for kw in data_keywords):
            if customer.current_data_gb > 0:
                search_query = f"{search_query} 데이터 {customer.current_data_gb}GB 이상 무제한"
            else:
                search_query = f"{search_query} 데이터 무제한 대용량"

        if conversation_context:
            search_query = f"{search_query} {conversation_context[:200]}"

        query_embedding = await _get_embedding(search_query)

        recommendations = await _search_with_collections(
            query_embedding=query_embedding,
            collection_names=collection_names,
            customer=customer,
            intent_label=intent_label,
            top_k=top_k
        )

        search_context = _generate_search_context(customer, intent_label, collection_names)

        return RAGPolicyResult(
            intent_label=intent_label,
            query=customer_query,
            searched_classifications=collection_names,
            recommendations=recommendations,
            search_context=search_context,
        )

    except Exception as e:
        logger.error(f"[RAG] 정책 검색 실패: {e}", exc_info=True)
        return RAGPolicyResult(
            intent_label=intent_label,
            query=customer_query,
            searched_classifications=[],
            recommendations=[],
            search_context="",
            error=str(e),
        )


# =============================================================================
# 노드 생성 함수
# =============================================================================

def create_summarize_node(llm: BaseChatModel):
    """요약 노드를 생성합니다."""
    structured_llm = llm.with_structured_output(SummaryResult)
    logger.debug("Pydantic 구조화 출력용 Structured LLM 생성 완료 (요약)")

    async def summarize_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        logger.debug("[에이전트] 요약 노드 시작")
        conversation_history = state.get("conversation_history", [])
        last_summarized_index = state.get("last_summarized_index", 0)
        current_summary = state.get("current_summary", "")
        existing_summary_result = state.get("summary_result", {})

        total_count = len(conversation_history)
        if last_summarized_index >= total_count:
            logger.debug("[에이전트] 새로운 대화 없음, 기존 요약 유지")
            return {
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        new_entries = conversation_history[last_summarized_index:]
        new_last_index = total_count
        new_conversation_text = _format_conversation_text(new_entries)

        previous_summary_text = "없음"
        try:
            if existing_summary_result:
                prev = SummaryResult.model_validate(existing_summary_result)
                previous_summary_text = (
                    f"- summary: {prev.summary}\n"
                    f"- customer_issue: {prev.customer_issue}\n"
                    f"- agent_action: {prev.agent_action}"
                )
        except Exception:
            previous_summary_text = "없음"

        user_content = f"""[이전 요약]
{previous_summary_text}

[새로 추가된 대화]
{new_conversation_text}"""

        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{SUMMARIZE_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        logger.debug("[에이전트] 요약 LLM 호출 중...")
        try:
            result = await structured_llm.ainvoke(messages)
            latest_summary = (
                result if isinstance(result, SummaryResult) else SummaryResult.model_validate(result)
            )
            summary_json = latest_summary.model_dump_json(ensure_ascii=False)
        except Exception as e:
            logger.error(f"[에이전트] 요약 노드 LLM 호출 실패: {e}")
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


def create_intent_node(llm: BaseChatModel):
    """의도 분석 노드를 생성합니다."""
    structured_llm = llm.with_structured_output(IntentResult)
    logger.debug("Pydantic 구조화 출력용 Structured LLM 생성 완료 (의도파악)")

    async def intent_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        last_intent_index = state.get("last_intent_index", 0)
        has_new_customer_turn = state.get("has_new_customer_turn", False)

        if not has_new_customer_turn:
            has_new_customer_turn = _has_customer_turn_since(
                conversation_history, last_intent_index
            )

        if not has_new_customer_turn:
            logger.info("[에이전트] 새로운 고객 발화 없음, 의도 분석 스킵")
            return {"last_intent_index": len(conversation_history)}

        recent = conversation_history[-6:]
        convo_text = _format_conversation_text(recent)

        user_content = f"""[최근 대화]
{convo_text}"""

        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{INTENT_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result = await structured_llm.ainvoke(messages)
            intent_model = (
                result if isinstance(result, IntentResult) else IntentResult.model_validate(result)
            )
            return {
                "intent_result": intent_model.model_dump(),
                "last_intent_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"[에이전트] 의도 노드 LLM 호출 실패: {e}")
            return {"last_intent_index": len(conversation_history)}

    return intent_node


def create_sentiment_node(llm: BaseChatModel):
    """감정 분석 노드를 생성합니다."""
    structured_llm = llm.with_structured_output(SentimentResult)
    logger.debug("Pydantic 구조화 출력용 Structured LLM 생성 완료 (감정분석)")

    async def sentiment_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        last_sentiment_index = state.get("last_sentiment_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_sentiment_index
        )

        if not has_new_customer_turn:
            logger.debug("[에이전트] 새로운 고객 발화 없음, 감정 분석 스킵")
            return {"last_sentiment_index": len(conversation_history)}

        recent_user_utts = [
            e for e in conversation_history[-8:]
            if e.get("speaker_name", "").startswith("고객") or e.get("speaker_id", "").startswith("user")
        ] or conversation_history[-4:]

        convo_text = _format_conversation_text(recent_user_utts)

        user_content = f"""[최근 고객 발화]
{convo_text}"""

        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{SENTIMENT_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result = await structured_llm.ainvoke(messages)
            sentiment_model = (
                result if isinstance(result, SentimentResult) else SentimentResult.model_validate(result)
            )
            return {
                "sentiment_result": sentiment_model.model_dump(),
                "last_sentiment_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"[에이전트] 감정 노드 LLM 호출 실패: {e}")
            return {"last_sentiment_index": len(conversation_history)}

    return sentiment_node


def create_draft_reply_node(llm: BaseChatModel):
    """응답 초안 생성 노드를 생성합니다."""
    structured_llm = llm.with_structured_output(DraftReplyResult)
    logger.debug("Pydantic 구조화 출력용 Structured LLM 생성 완료 (응답 초안 추천)")

    async def draft_reply_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        last_draft_index = state.get("last_draft_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_draft_index
        )

        if not has_new_customer_turn:
            logger.info("[에이전트] 새로운 고객 발화 없음, 응답 초안 생성 스킵")
            return {"last_draft_index": len(conversation_history)}

        recent = conversation_history[-8:]
        convo_text = _format_conversation_text(recent)

        intent = state.get("intent_result") or {}
        sentiment = state.get("sentiment_result") or {}

        user_content = f"""[최근 대화]
{convo_text}

[현재 인식된 의도]
{intent}

[현재 인식된 감정]
{sentiment}"""

        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{DRAFT_REPLY_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result = await structured_llm.ainvoke(messages)
            draft_model = (
                result if isinstance(result, DraftReplyResult) else DraftReplyResult.model_validate(result)
            )
            return {
                "draft_replies": draft_model.model_dump(),
                "last_draft_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"[에이전트] 응답 초안 노드 LLM 호출 실패: {e}")
            return {"last_draft_index": len(conversation_history)}

    return draft_reply_node


def create_risk_node(llm: BaseChatModel):
    """위험 감지 노드를 생성합니다."""
    structured_llm = llm.with_structured_output(RiskResult)
    logger.debug("Pydantic 구조화 출력용 Structured LLM 생성 완료 (위험 대응 경고)")

    async def risk_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return {}

        last_risk_index = state.get("last_risk_index", 0)
        has_new_customer_turn = _has_customer_turn_since(
            conversation_history, last_risk_index
        )

        if not has_new_customer_turn:
            logger.info("[에이전트] 새로운 고객 발화 없음, 위험 감지 스킵")
            return {"last_risk_index": len(conversation_history)}

        recent = conversation_history[-12:]
        convo_text = _format_conversation_text(recent)

        user_content = f"""[최근 대화]
{convo_text}"""

        base_context = runtime.context.get_system_message() or ""
        system_prompt = f"{RISK_SYSTEM_PROMPT}\n\n{base_context}".strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        try:
            result = await structured_llm.ainvoke(messages)
            risk_model = (
                result if isinstance(result, RiskResult) else RiskResult.model_validate(result)
            )

            if not risk_model.risk_flags:
                logger.debug("[에이전트] 위험 감지 없음, 결과 스킵")
                return {"last_risk_index": len(conversation_history)}

            return {
                "risk_result": risk_model.model_dump(),
                "last_risk_index": len(conversation_history)
            }
        except Exception as e:
            logger.error(f"[에이전트] 위험 감지 노드 LLM 호출 실패: {e}")
            return {"last_risk_index": len(conversation_history)}

    return risk_node


def create_rag_policy_node():
    """RAG 정책 검색 노드를 생성합니다."""

    async def rag_policy_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        """의도 기반 RAG 정책 검색 노드."""
        conversation_history = state.get("conversation_history", [])
        intent_result = state.get("intent_result", {})
        customer_info = state.get("customer_info", {})
        last_rag_index = state.get("last_rag_index", 0)
        last_rag_intent = state.get("last_rag_intent", "")

        if not intent_result:
            logger.info("[RAG] 의도 결과 없음, 스킵")
            return {"last_rag_index": len(conversation_history)}

        intent_label = intent_result.get("intent_label", "")
        intent_confidence = intent_result.get("intent_confidence", 0.0)

        if intent_label and intent_label == last_rag_intent:
            logger.info(f"[RAG] 동일 의도 '{intent_label}', 중복 검색 스킵")
            return {
                "rag_policy_result": {
                    "skipped": True,
                    "skip_reason": "동일한 의도로 이미 검색된 결과가 있습니다.",
                    "intent_label": intent_label
                },
                "last_rag_index": len(conversation_history)
            }

        recent_customer_utts = []
        for entry in reversed(conversation_history[-6:]):
            speaker_name = entry.get("speaker_name", "")
            is_customer = entry.get("is_customer", False)
            if is_customer or speaker_name.startswith("고객"):
                recent_customer_utts.insert(0, entry.get("text", ""))
                if len(recent_customer_utts) >= 2:
                    break
        customer_query = " ".join(recent_customer_utts)

        if not _should_trigger_rag(intent_label, customer_query, intent_confidence):
            logger.info(f"[RAG] 검색 불필요: 의도='{intent_label}' (신뢰도={intent_confidence:.2f})")
            return {
                "rag_policy_result": {
                    "skipped": True,
                    "skip_reason": "RAG 검색이 필요하지 않은 의도입니다.",
                    "intent_label": intent_label
                },
                "last_rag_index": len(conversation_history)
            }

        logger.info(f"[RAG] 정책 검색 중: 의도='{intent_label}'")

        try:
            rag_result = await rag_policy_search(
                intent_label=intent_label,
                customer_query=customer_query,
                customer_info=customer_info,
                top_k=5
            )
            result_dict = rag_result.to_dict()
            result_dict["skipped"] = False

            logger.info(f"[RAG] 검색 완료: {len(rag_result.recommendations)}개 추천")

            return {
                "rag_policy_result": result_dict,
                "last_rag_index": len(conversation_history),
                "last_rag_intent": intent_label
            }
        except Exception as e:
            logger.error(f"[RAG] 정책 검색 실패: {e}")
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


def create_faq_search_node():
    """FAQ Semantic Cache 검색 노드를 생성합니다."""

    async def faq_search_node(state: Any, runtime: Runtime) -> Dict[str, Any]:
        """FAQ semantic cache 검색 노드."""
        from modules.database import get_faq_service

        conversation_history = state.get("conversation_history", [])
        last_faq_index = state.get("last_faq_index", 0)
        last_faq_query = state.get("last_faq_query", "")
        shown_faq_ids = set(state.get("shown_faq_ids", []))

        has_new_customer = _has_customer_turn_since(conversation_history, last_faq_index)
        if not has_new_customer:
            logger.debug("[FAQ] 새로운 고객 발화 없음, 스킵")
            return {"last_faq_index": len(conversation_history)}

        recent_customer_utts = []
        for entry in reversed(conversation_history[-6:]):
            speaker_name = entry.get("speaker_name", "")
            is_customer = entry.get("is_customer", False)
            if is_customer or speaker_name.startswith("고객"):
                recent_customer_utts.insert(0, entry.get("text", ""))
                if len(recent_customer_utts) >= 2:
                    break
        customer_query = " ".join(recent_customer_utts)

        if not customer_query.strip():
            logger.debug("[FAQ] 고객 발화 텍스트 없음, 스킵")
            return {"last_faq_index": len(conversation_history)}

        if last_faq_query and _is_similar_query(customer_query, last_faq_query):
            logger.debug(f"[FAQ] 유사 쿼리 중복, 스킵: '{customer_query[:30]}...'")
            return {
                "faq_result": {
                    "skipped": True,
                    "skip_reason": "유사한 질문으로 이미 검색된 결과가 있습니다.",
                    "query": customer_query
                },
                "last_faq_index": len(conversation_history)
            }

        should_search = _should_trigger_faq_by_text(customer_query)
        if not should_search:
            logger.debug(f"[FAQ] 검색 불필요: 쿼리='{customer_query[:30]}...'")
            return {
                "faq_result": {
                    "skipped": True,
                    "skip_reason": "FAQ 검색이 필요하지 않은 발화입니다.",
                    "query": customer_query
                },
                "last_faq_index": len(conversation_history)
            }

        logger.debug(f"[FAQ] 검색 중: 쿼리='{customer_query[:50]}...'")

        try:
            faq_service = get_faq_service()
            if not faq_service.is_initialized:
                await faq_service.initialize()

            result = await faq_service.semantic_search(
                query=customer_query,
                limit=5,
                use_cache=True,
                distance_threshold=0.45,
            )

            new_faqs = []
            new_faq_ids = []
            for faq in result.faqs:
                faq_id = faq.get("id") or faq.get("faq_id") or faq.get("question", "")[:50]
                if faq_id not in shown_faq_ids:
                    new_faqs.append(faq)
                    new_faq_ids.append(faq_id)
                    if len(new_faqs) >= 3:
                        break

            if not new_faqs:
                logger.debug("[FAQ] 새로운 FAQ 없음 (모두 중복), 스킵")
                return {
                    "faq_result": {
                        "skipped": True,
                        "skip_reason": "이미 안내된 FAQ입니다.",
                        "query": customer_query
                    },
                    "last_faq_index": len(conversation_history)
                }

            updated_shown_ids = list(shown_faq_ids | set(new_faq_ids))

            faq_result = {
                "skipped": False,
                "query": customer_query,
                "cache_hit": result.cache_hit,
                "similarity_score": result.similarity_score,
                "cached_query": result.cached_query,
                "search_time_ms": result.search_time_ms,
                "faqs": new_faqs,
            }

            logger.debug(
                f"[FAQ] 검색 완료: {len(new_faqs)}개 (필터 전 {len(result.faqs)}개, "
                f"캐시={result.cache_hit}, 유사도={result.similarity_score:.3f})"
            )

            return {
                "faq_result": faq_result,
                "last_faq_index": len(conversation_history),
                "last_faq_query": customer_query,
                "shown_faq_ids": updated_shown_ids,
            }

        except Exception as e:
            logger.error(f"[FAQ] 검색 실패: {e}")
            return {
                "faq_result": {
                    "skipped": False,
                    "query": customer_query,
                    "faqs": [],
                    "error": str(e)
                },
                "last_faq_index": len(conversation_history)
            }

    return faq_search_node
