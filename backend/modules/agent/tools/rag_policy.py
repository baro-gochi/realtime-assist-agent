"""RAG 기반 정책/문구 자동 추천 도구.

고객 의도를 기반으로 pgvector에서 관련 정책, 요금제, 스크립트를 검색하여
상담사에게 실시간으로 제공합니다.

주요 기능:
    - 의도 기반 컬렉션 자동 선택
    - 멀티 컬렉션 병렬 검색
    - 정책 문구 및 설명 템플릿 반환

사용 예:
    >>> result = await rag_policy_search(
    ...     intent_label="요금 고지 문자 해석 요청",
    ...     customer_query="문자에는 89000원이라고 찍혔는데 왜 이 가격이죠?",
    ...     top_k=3
    ... )
    >>> print(result.recommendations)
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------- 실제 컬렉션 및 분류 정보 ----------
# 컬렉션 목록 (langchain_pg_embedding, 1536차원, text-embedding-3-small)
# - kt_mobile_plans (43개) - 모바일 요금제
# - kt_internet_plans (35개) - 인터넷 요금제
# - kt_tv_plans (21개) - TV 요금제
# - kt_bundle_discount (17개) - 결합 할인
# - kt_mobile_penalty (9개) - 위약금/해지
# - kt_membership (6개) - 멤버십 혜택
#
# 메타데이터 키:
# - name: 상품명
# - monthly_price_numeric: 월 요금 (숫자)
# - target_segment: 대상 고객층
# - price_sensitivity: 가격 민감도 (가성비, 프리미엄 등)
# - product_type: mobile, internet, tv, bundle 등
# - search_text: 검색 키워드

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

# RAG 검색이 필요한 의도 키워드 (이 키워드가 포함된 의도일 때만 RAG tool 호출)
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

# 의도 → 컬렉션 매핑 (실제 DB 컬렉션 사용)
INTENT_COLLECTION_MAP: Dict[str, List[str]] = {
    # 요금/청구 관련 - 모바일 요금제 검색
    "요금 조회": ["mobile"],
    "요금제 변경": ["mobile"],
    "요금제 추천": ["mobile"],
    "요금 고지 문자 해석 요청": ["mobile"],
    "청구서 문의": ["mobile"],
    "데이터 초과 요금": ["mobile"],

    # 결합/할인 관련
    "결합할인 문의": ["bundle", "internet", "tv"],
    "가족결합 문의": ["bundle"],
    "인터넷 결합": ["bundle", "internet"],
    "TV 결합": ["bundle", "tv"],

    # 요금제 상품
    "5G 요금제": ["mobile"],
    "LTE 요금제": ["mobile"],

    # 인터넷/TV 서비스
    "인터넷 요금제": ["internet"],
    "TV 서비스": ["tv"],

    # 위약금/해지/약정
    "위약금 문의": ["penalty"],
    "해지 문의": ["penalty"],
    "약정 문의": ["penalty"],

    # 멤버십
    "멤버십 문의": ["membership"],
    "포인트 문의": ["membership"],

    # 기본값 (의도 미매칭 시)
    "default": ["mobile", "bundle"],
}

# 키워드 기반 컬렉션 매칭 (의도 라벨이 정확하지 않을 때 보조)
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
    current_data_gb: int = 0  # 현재 요금제 데이터량 (GB, 0=무제한)

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
        """고객 특성을 기반으로 타겟 세그먼트 키워드를 추출합니다.

        Returns:
            고객과 매칭될 수 있는 세그먼트 키워드 목록
        """
        segments = []

        # 나이 기반 세그먼트
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

        # 멤버십 등급 기반 세그먼트
        if self.membership_grade:
            grade = self.membership_grade.upper()
            if grade in ["VVIP", "VIP"]:
                segments.extend(["프리미엄", "헤비유저", "고객"])
            elif grade == "GENERAL":
                segments.extend(["가성비", "저사용자"])

        # 요금 기반 세그먼트
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

    collection: str  # 출처 카테고리
    title: str  # 정책/상품명
    content: str  # 정책 내용 또는 설명 문구
    relevance_score: float  # 관련도 점수 (0~1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 추천 이유 (고객 상황 기반)
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
    searched_classifications: List[str]  # 검색에 사용된 분류 필터
    recommendations: List[PolicyRecommendation]
    search_context: str = ""  # 검색 컨텍스트 설명
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


def should_trigger_rag(intent_label: str, query: str) -> bool:
    """의도와 쿼리를 분석하여 RAG 검색이 필요한지 판단합니다.

    Returns:
        True if RAG search should be triggered, False otherwise
    """
    combined_text = f"{intent_label} {query}".lower()

    for keyword in RAG_TRIGGERING_KEYWORDS:
        if keyword.lower() in combined_text:
            return True

    return False


def _get_collections_for_intent(intent_label: str, query: str) -> List[str]:
    """의도와 쿼리를 분석하여 검색할 컬렉션 목록을 반환합니다."""
    collection_keys = set()

    # 1. 의도 라벨로 매칭
    if intent_label in INTENT_COLLECTION_MAP:
        collection_keys.update(INTENT_COLLECTION_MAP[intent_label])

    # 2. 의도 라벨에 포함된 키워드로 매칭
    for keyword, cols in KEYWORD_COLLECTION_MAP.items():
        if keyword in intent_label:
            collection_keys.update(cols)

    # 3. 쿼리에 포함된 키워드로 매칭
    for keyword, cols in KEYWORD_COLLECTION_MAP.items():
        if keyword in query:
            collection_keys.update(cols)

    # 4. 아무것도 매칭되지 않으면 기본값
    if not collection_keys:
        collection_keys.update(INTENT_COLLECTION_MAP["default"])

    # 컬렉션 키를 실제 컬렉션 이름으로 변환
    collection_names = [COLLECTIONS[key] for key in collection_keys if key in COLLECTIONS]
    return collection_names


def _generate_recommendation_reason(
    rec: PolicyRecommendation,
    customer: CustomerContext,
    intent_label: str
) -> str:
    """고객 상황을 기반으로 추천 이유를 생성합니다."""
    reasons = []

    # 가격 정보가 있는 경우 (새 메타데이터 구조)
    monthly_price = rec.metadata.get("monthly_price", 0)
    if monthly_price and customer.monthly_fee > 0:
        if monthly_price < customer.monthly_fee:
            diff = customer.monthly_fee - monthly_price
            reasons.append(f"현재 요금({customer.monthly_fee:,}원) 대비 월 {diff:,}원 절감 가능")
        elif monthly_price == customer.monthly_fee:
            reasons.append("현재 요금과 동일한 가격대")

    # 타겟 고객층 관련
    target_segment = rec.metadata.get("target_segment", "")
    if target_segment:
        # 고객 멤버십 등급이 타겟에 포함되어 있는지 확인
        if customer.membership_grade and customer.membership_grade in target_segment:
            reasons.append(f"{customer.membership_grade} 고객 대상 상품")
        elif "프리미엄" in target_segment and customer.membership_grade in ["VIP", "VVIP"]:
            reasons.append("프리미엄 고객 대상 상품")
        elif "가성비" in target_segment:
            reasons.append("가성비 추구 고객 추천")

    # 결합 상품 관련
    if "결합" in intent_label or rec.collection == "kt_bundle_discount":
        if customer.bundle_info:
            if "없음" in customer.bundle_info or "단독" in customer.bundle_info:
                reasons.append("현재 결합 미가입, 결합 시 추가 할인 가능")
            else:
                reasons.append("기존 결합 상품과 연계 가능")

    # 약정 상태 관련
    if "약정" in intent_label or "위약금" in intent_label or rec.collection == "kt_mobile_penalty":
        if "무약정" in customer.contract_status:
            reasons.append("무약정 상태로 요금제 변경 자유로움")
        elif "약정" in customer.contract_status:
            reasons.append("현재 약정 상태 확인 필요")

    return " / ".join(reasons) if reasons else "고객 문의 내용과 관련된 정보"


async def _search_with_collections(
    query_embedding: List[float],
    collection_names: List[str],
    customer: CustomerContext,
    intent_label: str,
    top_k: int = 5,
) -> List[PolicyRecommendation]:
    """컬렉션 필터를 적용하여 벡터 검색을 수행합니다.

    고객 정보를 활용한 스마트 검색:
    - 비용 절감 의도: 현재 요금보다 저렴한 요금제 우선
    - 결합 문의: 고객의 결합 상태에 맞는 정보
    - 멤버십: 고객 등급에 맞는 혜택
    """
    from modules.database import get_db_manager

    try:
        db = get_db_manager()
        if not db.is_initialized:
            logger.warning("[RAG] DB 초기화 안됨, 검색 스킵")
            return []

        # pgvector 코사인 유사도 검색
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # 컬렉션 필터 조건 구성
        if collection_names:
            collection_filter = " OR ".join([
                f"c.name = '{col}'"
                for col in collection_names
            ])
            where_clause = f"({collection_filter})"
        else:
            # 컬렉션이 없으면 모바일 요금제 기본값
            where_clause = "c.name = 'kt_mobile_plans'"

        # 현재 고객의 요금제 제외 (동일 요금제 추천 방지)
        if customer.current_plan:
            # SQL 인젝션 방지를 위해 특수문자 이스케이프
            safe_plan_name = customer.current_plan.replace("'", "''")
            where_clause += f" AND (e.cmetadata->>'name' IS NULL OR e.cmetadata->>'name' != '{safe_plan_name}')"

        # 요금제 관련 검색 여부 (스마트 정렬 적용 대상)
        plan_collections = {"kt_mobile_plans", "kt_internet_plans", "kt_tv_plans"}
        is_plan_search = bool(
            set(collection_names) & plan_collections
        ) if collection_names else True

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

            # 가격 정보 (월 요금)
            monthly_price = metadata.get("monthly_price_numeric", 0)

            # document 필드에서 plan_details 파싱
            plan_details = {}
            document_raw = row["document"]
            if document_raw:
                try:
                    import json
                    import re
                    # "상세 정보:" 이후의 JSON 부분 추출
                    json_match = re.search(r'상세 정보:\s*(\{.*\})\s*$', document_raw, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        doc_data = json.loads(json_str)
                        if isinstance(doc_data, dict):
                            plan_details = doc_data.get("plan_details", {})
                            # name이 document에 있으면 사용
                            if not title or title == "정책 문서":
                                title = doc_data.get("name", title)
                            # monthly_price_numeric이 document에 있으면 사용
                            if not monthly_price:
                                monthly_price = doc_data.get("monthly_price_numeric", 0)
                    else:
                        # 전체가 JSON인 경우 시도
                        doc_data = json.loads(document_raw)
                        if isinstance(doc_data, dict):
                            plan_details = doc_data.get("plan_details", {})
                            if not title or title == "정책 문서":
                                title = doc_data.get("name", title)
                            if not monthly_price:
                                monthly_price = doc_data.get("monthly_price_numeric", 0)
                except (json.JSONDecodeError, TypeError):
                    # JSON 파싱 실패시 무시
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

            # 추천 이유 생성
            rec.recommendation_reason = _generate_recommendation_reason(
                rec, customer, intent_label
            )

            results.append(rec)

        # 스마트 정렬: 요금제 검색 시 고객 세그먼트 매칭 기반 정렬
        if is_plan_search:
            results = _sort_by_customer_fit(results, customer)

        return results[:top_k]

    except Exception as e:
        logger.error(f"[RAG] 검색 실패: {e}")
        return []


def _parse_data_amount_from_text(search_text: str) -> int:
    """search_text에서 데이터량(GB)을 파싱합니다.

    Returns:
        데이터량 (GB 단위), 무제한은 9999, 파싱 실패 시 0
    """
    import re

    if not search_text:
        return 0

    text_lower = search_text.lower()

    # 무제한 체크
    if "무제한" in text_lower or "unlimited" in text_lower:
        return 9999

    # 숫자+GB 패턴 찾기 (예: "110GB", "11GB", "데이터 50GB")
    match = re.search(r'(\d+)\s*(?:gb|기가)', text_lower)
    if match:
        return int(match.group(1))

    return 0


def _calculate_segment_match_score(
    target_segment: str,
    price_sensitivity: str,
    customer_segments: List[str]
) -> int:
    """고객 세그먼트와 요금제 타겟 세그먼트의 매칭 점수를 계산합니다.

    Returns:
        매칭된 키워드 개수 (높을수록 좋음)
    """
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
    """고객 특성에 맞는 요금제 순으로 정렬합니다.

    정렬 우선순위:
    1. 데이터량 적합성 (현재보다 많은 데이터 제공 요금제 우선)
    2. 타겟 세그먼트 매칭 점수 (높을수록 우선)
    3. 현재 요금보다 저렴하면서 50% 이상인 요금제
    4. 벡터 유사도 점수
    """
    customer_segments = customer.get_customer_segments()
    current_fee = customer.monthly_fee
    current_data = customer.current_data_gb  # 0=무제한 또는 알 수 없음

    def calculate_sort_key(rec: PolicyRecommendation) -> tuple:
        # 0. 데이터량 적합성 점수 (고객이 더 많은 데이터를 원할 때)
        search_text = rec.metadata.get("search_text", "")
        plan_data = _parse_data_amount_from_text(search_text)

        if current_data > 0 and plan_data > 0:
            # 고객 현재 데이터량보다 많은지 확인
            if plan_data >= current_data:
                # 무제한(9999)이면 최우선, 그 외는 데이터량 차이로 정렬
                data_score = 0 if plan_data == 9999 else 1
            else:
                # 현재보다 적은 데이터는 후순위
                data_score = 3
        elif plan_data == 9999:
            # 무제한은 항상 좋음
            data_score = 0
        else:
            # 데이터 정보 없음
            data_score = 2

        # 1. 세그먼트 매칭 점수 (음수: 높을수록 앞으로)
        target_segment = rec.metadata.get("target_segment", "")
        price_sensitivity = rec.metadata.get("price_sensitivity", "")
        segment_score = -_calculate_segment_match_score(
            target_segment, price_sensitivity, customer_segments
        )

        # 2. 가격 적정성 점수
        price = rec.metadata.get("monthly_price", 0) or 0
        if current_fee > 0 and price > 0:
            ratio = price / current_fee
            # 50%~150% 범위가 적정 (업그레이드 포함)
            if 0.5 <= ratio <= 1.5:
                price_score = 0
            elif ratio < 0.5:
                price_score = 1  # 너무 저렴 (급격한 다운그레이드)
            else:
                price_score = 2  # 너무 비쌈
        else:
            price_score = 1

        # 3. 벡터 유사도 (음수: 높을수록 앞으로)
        similarity_score = -(rec.relevance_score or 0)

        return (data_score, segment_score, price_score, similarity_score)

    return sorted(results, key=calculate_sort_key)


async def _get_embedding(text: str) -> List[float]:
    """텍스트의 임베딩 벡터를 생성합니다."""
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vector = await embeddings.aembed_query(text)
    return vector


async def _get_all_membership_grades() -> List[PolicyRecommendation]:
    """모든 멤버십 등급 정보를 등급 순서대로 가져옵니다."""
    from modules.database import get_db_manager

    try:
        db = get_db_manager()
        if not db.is_initialized:
            return []

        query = """
            SELECT
                e.document,
                e.cmetadata
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
    """고객 의도 기반 RAG 정책 검색을 수행합니다.

    Args:
        intent_label: 분석된 고객 의도 라벨 (예: "요금 고지 문자 해석 요청")
        customer_query: 고객의 원본 질문
        customer_info: 고객 정보 딕셔너리 (monthly_fee, current_plan 등)
        conversation_context: 대화 맥락 (선택)
        top_k: 반환할 결과 수

    Returns:
        RAGPolicyResult: 검색 결과 (추천 이유 포함)

    스마트 검색 기능:
        - 비용 절감 의도: 현재 요금보다 저렴한 요금제 우선 추천
        - 결합 문의: 고객 결합 상태 기반 추천
        - 멤버십: 등급 기반 혜택 정보 우선
    """
    try:
        # 1. 고객 컨텍스트 생성
        customer = CustomerContext.from_dict(customer_info or {})

        # 2. 검색할 컬렉션 결정
        collection_names = _get_collections_for_intent(intent_label, customer_query)
        logger.info(
            f"[RAG] 검색 시작: 의도='{intent_label}', "
            f"컬렉션={collection_names}, "
            f"월요금={customer.monthly_fee}"
        )

        # 2-1. 멤버십 등급 문의인 경우 전체 등급 정보를 표로 제공
        is_membership_grade_query = (
            "membership" in collection_names and
            any(kw in f"{intent_label} {customer_query}".lower()
                for kw in ["등급", "기준", "조건", "vvip", "vip", "gold", "silver"])
        )

        if is_membership_grade_query:
            # 멤버십 등급 전체 조회
            all_grades = await _get_all_membership_grades()
            if all_grades:
                # 첫 번째 결과에 전체 등급표를 포함
                grade_table = _format_membership_table(all_grades)
                search_context = _generate_search_context(
                    customer, intent_label, collection_names
                )
                search_context = f"{search_context}\n\n{grade_table}"

                return RAGPolicyResult(
                    intent_label=intent_label,
                    query=customer_query,
                    searched_classifications=collection_names,
                    recommendations=all_grades,
                    search_context=search_context,
                )

        # 3. 검색 쿼리 구성 (고객 요금제 정보 포함)
        search_query = f"{intent_label} {customer_query}"
        if customer.current_plan:
            search_query = f"{search_query} 현재 {customer.current_plan}"

        # 데이터량 요구사항 추가 (더 많은 데이터 요청 시)
        data_keywords = ["많은", "더", "늘리", "부족", "초과", "무제한", "대용량"]
        query_lower = customer_query.lower()
        if any(kw in query_lower for kw in data_keywords):
            if customer.current_data_gb > 0:
                search_query = f"{search_query} 데이터 {customer.current_data_gb}GB 이상 무제한"
            else:
                search_query = f"{search_query} 데이터 무제한 대용량"

        if conversation_context:
            search_query = f"{search_query} {conversation_context[:200]}"

        # 4. 임베딩 생성
        query_embedding = await _get_embedding(search_query)

        # 5. 컬렉션 필터 적용하여 검색 (고객 정보 기반 스마트 정렬)
        recommendations = await _search_with_collections(
            query_embedding=query_embedding,
            collection_names=collection_names,
            customer=customer,
            intent_label=intent_label,
            top_k=top_k
        )

        # 6. 검색 컨텍스트 생성
        search_context = _generate_search_context(customer, intent_label, collection_names)

        return RAGPolicyResult(
            intent_label=intent_label,
            query=customer_query,
            searched_classifications=collection_names,  # 컬렉션 이름 반환
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


# LangGraph Tool 래퍼
@tool
async def rag_policy_tool(
    intent_label: str,
    customer_query: str,
    customer_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """고객 의도와 정보를 기반으로 관련 정책 문서를 검색합니다.

    Args:
        intent_label: 고객의 핵심 의도 (예: "요금제 변경", "결합할인 문의")
        customer_query: 고객의 원본 질문
        customer_info: 고객 정보 (monthly_fee, current_plan, membership_grade 등)

    Returns:
        검색된 정책 문서 (추천 이유 포함)
    """
    result = await rag_policy_search(
        intent_label=intent_label,
        customer_query=customer_query,
        customer_info=customer_info,
    )
    return result.to_dict()
