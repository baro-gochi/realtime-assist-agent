"""KT 멤버십 FAQ Redis 서비스.

FAQ 데이터를 Redis에 저장하고 빠르게 검색할 수 있도록 합니다.

Redis Schema:
    - kt:faq:all - 전체 FAQ 목록 (JSON)
    - kt:faq:category:{category} - 카테고리별 FAQ ID 목록
    - kt:faq:id:{id} - 개별 FAQ 데이터
    - kt:faq:keywords - 검색 키워드 Set

Semantic Cache:
    - 의미 기반 캐싱을 통해 유사한 질문에 대해 캐시된 결과 반환
    - semantic_search() 메서드 사용

Usage:
    >>> from modules.database import get_faq_service
    >>> faq_service = get_faq_service()
    >>> await faq_service.initialize()
    >>> # 키워드 기반 검색
    >>> results = await faq_service.search("VIP 등급")
    >>> # 의미 기반 검색 (캐싱 포함)
    >>> result = await faq_service.semantic_search("VIP 되려면 어떻게 해요?")
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .redis_connection import get_redis_manager

if TYPE_CHECKING:
    from .faq_cache import FAQCacheResult

logger = logging.getLogger(__name__)

# FAQ JSON 파일 경로
FAQ_JSON_PATH = Path(__file__).parent.parent.parent.parent / "data" / "kt_faq" / "kt_membership_faq.json"

# Redis 키 prefix
FAQ_PREFIX = "kt:faq"


class FAQService:
    """KT 멤버십 FAQ 서비스.

    FAQ 데이터를 Redis에 캐싱하고 키워드 기반 검색을 제공합니다.
    """

    _instance: Optional["FAQService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._faqs = []
            cls._instance._categories = set()
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self, force_reload: bool = False) -> bool:
        """FAQ 서비스를 초기화합니다.

        Args:
            force_reload: True면 기존 캐시를 무시하고 다시 로드

        Returns:
            bool: 초기화 성공 여부
        """
        if self._initialized and not force_reload:
            return True

        redis_mgr = get_redis_manager()
        if not redis_mgr.is_initialized:
            await redis_mgr.initialize()

        if not redis_mgr.is_initialized:
            logger.error("[FAQ] Redis 사용 불가, 초기화 불가")
            return False

        # Redis에 이미 데이터가 있는지 확인
        cached = await redis_mgr.get(f"{FAQ_PREFIX}:all")
        if cached and not force_reload:
            try:
                data = json.loads(cached)
                self._faqs = data.get("faqs", [])
                self._categories = set(faq.get("category", "") for faq in self._faqs)
                self._initialized = True
                logger.info(f"[FAQ] Redis 캐시에서 로드: {len(self._faqs)}개 항목")
                return True
            except json.JSONDecodeError:
                logger.warning("[FAQ] 캐시 데이터 유효하지 않음, 파일에서 다시 로드")

        # JSON 파일에서 로드
        return await self._load_from_file()

    async def _load_from_file(self) -> bool:
        """JSON 파일에서 FAQ를 로드하고 Redis에 캐싱합니다."""
        if not FAQ_JSON_PATH.exists():
            logger.error(f"[FAQ] JSON 파일 없음: {FAQ_JSON_PATH}")
            return False

        try:
            with open(FAQ_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._faqs = data.get("faqs", [])
            self._categories = set(faq.get("category", "") for faq in self._faqs)

            # Redis에 캐싱
            redis_mgr = get_redis_manager()

            # 전체 FAQ 저장
            await redis_mgr.set(f"{FAQ_PREFIX}:all", json.dumps(data, ensure_ascii=False))

            # 개별 FAQ 및 카테고리별 인덱스 저장
            category_map: dict[str, list[str]] = {}

            for faq in self._faqs:
                faq_id = faq.get("id", "")
                category = faq.get("category", "")

                # 개별 FAQ 저장
                await redis_mgr.client.set(
                    f"{FAQ_PREFIX}:id:{faq_id}",
                    json.dumps(faq, ensure_ascii=False)
                )

                # 카테고리별 그룹화
                if category not in category_map:
                    category_map[category] = []
                category_map[category].append(faq_id)

            # 카테고리별 인덱스 저장
            for category, faq_ids in category_map.items():
                await redis_mgr.client.set(
                    f"{FAQ_PREFIX}:category:{category}",
                    json.dumps(faq_ids, ensure_ascii=False)
                )

            self._initialized = True
            logger.info(f"[FAQ] 파일에서 로드 후 캐싱: {len(self._faqs)}개 항목, {len(self._categories)}개 카테고리")
            return True

        except Exception as e:
            logger.error(f"[FAQ] 파일 로드 실패: {e}")
            return False

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """키워드로 FAQ를 검색합니다.

        Args:
            query: 검색 쿼리
            limit: 최대 결과 수

        Returns:
            list[dict]: 관련도 순으로 정렬된 FAQ 목록
        """
        if not self._initialized:
            await self.initialize()

        if not query or not query.strip():
            return []

        query = query.strip().lower()
        keywords = set(re.split(r'\s+', query))

        results = []

        for faq in self._faqs:
            score = self._calculate_relevance(faq, query, keywords)
            if score > 0:
                results.append((score, faq))

        # 점수 순으로 정렬
        results.sort(key=lambda x: x[0], reverse=True)

        return [faq for _, faq in results[:limit]]

    async def search_grouped(
        self,
        query: str,
        limit: int = 10,
        max_per_category: int = 3,
    ) -> Dict[str, List[dict]]:
        """키워드로 FAQ를 검색하고 카테고리별로 그룹화합니다.

        Args:
            query: 검색 쿼리
            limit: 최대 총 결과 수
            max_per_category: 카테고리당 최대 결과 수

        Returns:
            Dict[str, List[dict]]: 카테고리별로 그룹화된 FAQ 목록
                {
                    "VVIP/VIP": [faq1, faq2],
                    "멤버십 혜택": [faq3, faq4],
                    ...
                }
        """
        if not self._initialized:
            await self.initialize()

        if not query or not query.strip():
            return {}

        query = query.strip().lower()
        keywords = set(re.split(r'\s+', query))

        # 점수와 함께 결과 수집
        results = []
        for faq in self._faqs:
            score = self._calculate_relevance(faq, query, keywords)
            if score > 0:
                results.append((score, faq))

        # 점수 순으로 정렬
        results.sort(key=lambda x: x[0], reverse=True)

        # 카테고리별 그룹화 (점수 순서 유지)
        grouped: Dict[str, List[dict]] = {}
        category_counts: Dict[str, int] = {}
        total_count = 0

        for score, faq in results:
            if total_count >= limit:
                break

            category = faq.get("category", "기타")
            if category not in grouped:
                grouped[category] = []
                category_counts[category] = 0

            if category_counts[category] < max_per_category:
                # 점수 정보를 FAQ에 추가
                faq_with_score = {**faq, "_score": score}
                grouped[category].append(faq_with_score)
                category_counts[category] += 1
                total_count += 1

        # 카테고리 순서 정렬 (가장 높은 점수의 FAQ가 있는 카테고리 먼저)
        category_max_scores = {
            cat: max(f.get("_score", 0) for f in faqs)
            for cat, faqs in grouped.items()
        }
        sorted_categories = sorted(
            grouped.keys(),
            key=lambda c: category_max_scores[c],
            reverse=True
        )

        return {cat: grouped[cat] for cat in sorted_categories}

    def _calculate_relevance(self, faq: dict, query: str, keywords: set[str]) -> float:
        """FAQ와 검색어의 관련도를 계산합니다."""
        score = 0.0

        question = faq.get("question", "").lower()
        answer = faq.get("answer", "").lower()
        category = faq.get("category", "").lower()

        # 전체 쿼리가 질문에 포함되면 높은 점수
        if query in question:
            score += 10.0

        # 전체 쿼리가 답변에 포함되면 중간 점수
        if query in answer:
            score += 5.0

        # 개별 키워드 매칭
        for keyword in keywords:
            if len(keyword) < 2:
                continue

            if keyword in question:
                score += 3.0
            if keyword in answer:
                score += 1.0
            if keyword in category:
                score += 2.0

        # 특정 키워드 부스트
        boost_keywords = {
            "vvip": ["vvip", "vip", "등급"],
            "vip": ["vip", "등급", "초이스"],
            "영화": ["영화", "롯데시네마", "cgv", "메가박스", "예매"],
            "스타벅스": ["스타벅스", "커피", "vip초이스"],
            "등급": ["등급", "vvip", "vip", "gold", "silver"],
            "포인트": ["포인트", "할인", "한도"],
            "카드": ["카드", "플라스틱", "모바일", "발급"],
            "내통장": ["내통장", "결제", "계좌"],
            "달달": ["달달", "혜택", "초이스", "스페셜"],
            "생일": ["생일", "혜택", "vvip"],
        }

        for main_kw, related_kws in boost_keywords.items():
            if main_kw in query:
                for related in related_kws:
                    if related in question or related in answer:
                        score += 0.5

        # 복합 키워드 부스트 (키워드 조합 시 높은 가중치)
        compound_boost = {
            ("vip", "혜택"): {
                "must_contain": ["vip"],  # 질문/답변에 반드시 포함
                "question_bonus": ["혜택"],  # 질문에 포함 시 추가 부스트
                "boost": 8.0,
                "question_boost": 5.0,  # 질문에 bonus 키워드 있으면 추가
            },
            ("vvip", "혜택"): {
                "must_contain": ["vvip"],
                "question_bonus": ["혜택"],
                "boost": 8.0,
                "question_boost": 5.0,
            },
            ("등급", "혜택"): {
                "must_contain": ["등급"],
                "question_bonus": ["혜택"],
                "boost": 5.0,
                "question_boost": 3.0,
            },
            ("달달", "혜택"): {
                "must_contain": ["달달"],
                "question_bonus": ["혜택"],
                "boost": 6.0,
                "question_boost": 3.0,
            },
            ("생일", "혜택"): {
                "must_contain": ["생일"],
                "question_bonus": ["혜택"],
                "boost": 6.0,
                "question_boost": 3.0,
            },
            ("포인트", "적립"): {
                "must_contain": ["포인트", "적립"],
                "boost": 5.0,
            },
            ("영화", "예매"): {
                "must_contain": ["영화"],
                "question_bonus": ["예매"],
                "boost": 5.0,
                "question_boost": 3.0,
            },
            ("영화", "할인"): {
                "must_contain": ["영화"],
                "question_bonus": ["할인"],
                "boost": 5.0,
                "question_boost": 3.0,
            },
        }

        for (kw1, kw2), config in compound_boost.items():
            if kw1 in query and kw2 in query:
                # must_contain 키워드가 질문/답변에 있는지 확인
                content = question + " " + answer
                if all(must_kw in content for must_kw in config["must_contain"]):
                    score += config["boost"]
                    # 질문에 bonus 키워드가 직접 포함된 경우 추가 부스트
                    if "question_bonus" in config and "question_boost" in config:
                        if any(bonus_kw in question for bonus_kw in config["question_bonus"]):
                            score += config["question_boost"]

        return score

    async def get_by_id(self, faq_id: str) -> Optional[dict]:
        """ID로 FAQ를 조회합니다."""
        if not self._initialized:
            await self.initialize()

        redis_mgr = get_redis_manager()
        cached = await redis_mgr.get(f"{FAQ_PREFIX}:id:{faq_id}")

        if cached:
            return json.loads(cached)

        # 캐시에 없으면 메모리에서 검색
        for faq in self._faqs:
            if faq.get("id") == faq_id:
                return faq

        return None

    async def get_by_category(self, category: str) -> list[dict]:
        """카테고리별 FAQ를 조회합니다."""
        if not self._initialized:
            await self.initialize()

        return [faq for faq in self._faqs if faq.get("category") == category]

    async def get_all_categories(self) -> list[str]:
        """모든 카테고리 목록을 반환합니다."""
        if not self._initialized:
            await self.initialize()

        return sorted(list(self._categories))

    async def get_all(self) -> list[dict]:
        """모든 FAQ를 반환합니다."""
        if not self._initialized:
            await self.initialize()

        return self._faqs

    async def reload(self) -> bool:
        """FAQ 데이터를 다시 로드합니다."""
        self._initialized = False
        return await self.initialize(force_reload=True)

    async def semantic_search(
        self,
        query: str,
        limit: int = 5,
        use_cache: bool = True,
        distance_threshold: float = 0.15,
    ) -> "FAQCacheResult":
        """의미 기반 FAQ 검색 (캐싱 포함).

        유사한 질문이 캐시에 있으면 캐시된 결과를 반환하고,
        없으면 키워드 검색 후 결과를 캐싱합니다.

        Args:
            query: 검색할 질문
            limit: 최대 결과 수
            use_cache: 캐시 사용 여부
            distance_threshold: 유사도 임계값 (낮을수록 엄격, 기본 0.15)

        Returns:
            FAQCacheResult: 검색 결과
                - cache_hit: 캐시 히트 여부
                - faqs: FAQ 검색 결과 리스트
                - similarity_score: 캐시 히트 시 유사도 점수
                - search_time_ms: 검색 소요 시간

        Examples:
            >>> result = await faq_service.semantic_search("VIP 되려면 어떻게 해요?")
            >>> if result.cache_hit:
            ...     print(f"Cache hit! similarity={result.similarity_score:.2f}")
            >>> for faq in result.faqs:
            ...     print(faq["question"])
        """
        from .faq_cache import get_faq_cache, FAQCacheResult

        if not self._initialized:
            await self.initialize()

        # 캐시 사용 안 함
        if not use_cache:
            faqs = await self.search(query, limit)
            return FAQCacheResult(
                query=query,
                faqs=faqs,
                cache_hit=False,
                similarity_score=0.0,
                cached_query="",
                search_time_ms=0.0,
            )

        # 캐시를 통한 검색
        cache = get_faq_cache()

        async def fallback_search(q: str, cat: Optional[str]) -> List[Dict[str, Any]]:
            """캐시 미스 시 키워드 검색 fallback."""
            return await self.search(q, limit)

        result = await cache.search_with_cache(
            query=query,
            fallback_search_func=fallback_search,
            similarity_threshold=distance_threshold,
        )

        return result

    async def get_cache_stats(self) -> Dict[str, Any]:
        """FAQ 캐시 통계를 반환합니다."""
        from .faq_cache import get_faq_cache

        cache = get_faq_cache()
        return await cache.get_cache_stats()


# 싱글톤 인스턴스 getter
def get_faq_service() -> FAQService:
    """FAQService 싱글톤 인스턴스를 반환합니다."""
    return FAQService()
