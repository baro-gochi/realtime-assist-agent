"""FAQ Semantic Cache Service (pgvector).

의미 기반 캐싱을 통해 유사한 질문에 대해 캐시된 FAQ 결과를 반환합니다.
pgvector를 사용하여 쿼리 임베딩을 저장하고 유사도 검색을 수행합니다.

Architecture:
    1. 사용자 질문 -> pgvector에서 유사 쿼리 검색
    2. 캐시 히트 -> 캐시된 FAQ 결과 반환 (빠름)
    3. 캐시 미스 -> FAQ 검색 -> pgvector에 캐싱 -> 결과 반환

PostgreSQL Schema:
    CREATE TABLE faq_query_cache (
        id SERIAL PRIMARY KEY,
        query_text TEXT NOT NULL,
        query_embedding vector(1536),
        category VARCHAR(100),
        faq_results JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        hit_count INTEGER DEFAULT 0
    );
    CREATE INDEX ON faq_query_cache USING ivfflat (query_embedding vector_cosine_ops);

Usage:
    >>> from modules.database import get_faq_cache
    >>> cache = get_faq_cache()
    >>> await cache.initialize()
    >>> result = await cache.search_with_cache("VIP 등급 조건이 뭐예요?", category="등급")
"""

import json
import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings

from .connection import get_db_manager

logger = logging.getLogger(__name__)

# Cache configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
SIMILARITY_THRESHOLD = 0.50  # Cosine similarity (lower for Korean semantic matching)
CACHE_TABLE = "faq_query_cache"


@dataclass
class FAQCacheResult:
    """FAQ 캐시 검색 결과."""

    query: str
    faqs: List[Dict[str, Any]]
    cache_hit: bool
    similarity_score: float = 0.0
    cached_query: str = ""  # 캐시 히트 시 원래 캐시된 쿼리
    search_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "faqs": self.faqs,
            "cache_hit": self.cache_hit,
            "similarity_score": self.similarity_score,
            "cached_query": self.cached_query,
            "search_time_ms": self.search_time_ms,
        }


class FAQSemanticCache:
    """FAQ 의미 기반 캐시 서비스 (pgvector).

    PostgreSQL pgvector를 사용하여 질문 임베딩을 저장하고,
    유사한 질문에 대해 캐시된 FAQ 결과를 반환합니다.
    """

    _instance: Optional["FAQSemanticCache"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._embeddings = None
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> bool:
        """캐시 서비스를 초기화합니다.

        Returns:
            bool: 초기화 성공 여부
        """
        if self._initialized:
            return True

        try:
            # DB 연결 확인
            db = get_db_manager()
            if not db.is_initialized:
                logger.error("Database not initialized for FAQ cache")
                return False

            # Embeddings 초기화
            self._embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

            # 캐시 테이블 생성 (없으면)
            await self._ensure_table_exists()

            self._initialized = True
            logger.info("FAQ Semantic Cache initialized (pgvector)")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize FAQ cache: {e}")
            self._initialized = False
            return False

    async def _ensure_table_exists(self):
        """캐시 테이블이 존재하는지 확인하고 없으면 생성합니다."""
        db = get_db_manager()

        # pgvector extension 확인
        await db.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # 테이블 생성
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
            id SERIAL PRIMARY KEY,
            query_text TEXT NOT NULL,
            query_embedding vector({EMBEDDING_DIM}),
            category VARCHAR(100),
            faq_results JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            hit_count INTEGER DEFAULT 0
        )
        """
        await db.execute(create_table_sql)

        # 인덱스 생성 (이미 있으면 무시)
        try:
            await db.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{CACHE_TABLE}_embedding
                ON {CACHE_TABLE}
                USING ivfflat (query_embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
        except Exception as e:
            # ivfflat 인덱스 생성 실패 시 (데이터 부족 등) 무시
            logger.debug(f"Index creation skipped: {e}")

        logger.debug(f"Cache table ensured: {CACHE_TABLE}")

    async def _get_embedding(self, text: str) -> List[float]:
        """텍스트의 임베딩 벡터를 생성합니다."""
        vector = await self._embeddings.aembed_query(text)
        return vector

    async def search_cache(
        self,
        query: str,
        category: Optional[str] = None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> Optional[FAQCacheResult]:
        """캐시에서 유사한 쿼리를 검색합니다.

        Args:
            query: 검색할 질문
            category: FAQ 카테고리 필터 (optional)
            similarity_threshold: 유사도 임계값 (높을수록 엄격, 1.0 = 동일)

        Returns:
            FAQCacheResult if cache hit, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        if not self._embeddings:
            return None

        try:
            start_time = time.time()
            db = get_db_manager()

            # 쿼리 임베딩 생성
            query_embedding = await self._get_embedding(query)
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            # 카테고리 필터 조건
            category_filter = ""
            if category:
                category_filter = f"AND category = '{category}'"

            # 코사인 유사도 검색 (1 - distance = similarity)
            # asyncpg에서 :: 캐스팅 대신 CAST() 사용
            search_sql = f"""
                SELECT
                    id,
                    query_text,
                    faq_results,
                    category,
                    1 - (query_embedding <=> CAST($1 AS vector)) as similarity
                FROM {CACHE_TABLE}
                WHERE query_embedding IS NOT NULL
                {category_filter}
                ORDER BY query_embedding <=> CAST($1 AS vector)
                LIMIT 1
            """

            row = await db.fetchrow(search_sql, embedding_str)

            search_time_ms = (time.time() - start_time) * 1000

            if not row:
                return None

            similarity = float(row["similarity"])

            # 유사도가 임계값 미만이면 캐시 미스
            if similarity < similarity_threshold:
                logger.debug(
                    f"Cache miss: similarity={similarity:.4f} < threshold={similarity_threshold}"
                )
                return None

            # 캐시 히트 - hit_count 증가
            await db.execute(
                f"UPDATE {CACHE_TABLE} SET hit_count = hit_count + 1 WHERE id = $1",
                row["id"]
            )

            # JSONB가 문자열로 반환될 수 있으므로 파싱
            faq_results = row["faq_results"]
            if isinstance(faq_results, str):
                cached_faqs = json.loads(faq_results)
            else:
                cached_faqs = faq_results or []
            cached_query = row["query_text"]

            logger.info(
                f"Cache hit: query='{query[:30]}...' "
                f"cached_query='{cached_query[:30]}...' "
                f"similarity={similarity:.4f}"
            )

            return FAQCacheResult(
                query=query,
                faqs=cached_faqs,
                cache_hit=True,
                similarity_score=similarity,
                cached_query=cached_query,
                search_time_ms=search_time_ms,
            )

        except Exception as e:
            logger.error(f"Cache search failed: {e}")
            return None

    async def cache_result(
        self,
        query: str,
        faqs: List[Dict[str, Any]],
        category: Optional[str] = None,
    ) -> bool:
        """FAQ 검색 결과를 캐시에 저장합니다.

        Args:
            query: 원본 질문
            faqs: FAQ 검색 결과 리스트
            category: FAQ 카테고리

        Returns:
            bool: 캐싱 성공 여부
        """
        if not self._initialized:
            await self.initialize()

        if not self._embeddings:
            return False

        try:
            db = get_db_manager()

            # 쿼리 임베딩 생성
            query_embedding = await self._get_embedding(query)
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            # 캐시에 저장 (asyncpg에서 CAST 사용)
            insert_sql = f"""
                INSERT INTO {CACHE_TABLE} (query_text, query_embedding, category, faq_results)
                VALUES ($1, CAST($2 AS vector), $3, $4)
            """

            await db.execute(
                insert_sql,
                query,
                embedding_str,
                category or "general",
                json.dumps(faqs, ensure_ascii=False),
            )

            logger.debug(f"Cached FAQ result: query='{query[:50]}...', faqs={len(faqs)}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache result: {e}")
            return False

    async def search_with_cache(
        self,
        query: str,
        category: Optional[str] = None,
        fallback_search_func=None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> FAQCacheResult:
        """캐시를 확인하고, 미스 시 fallback 검색을 수행합니다.

        Args:
            query: 검색할 질문
            category: FAQ 카테고리 필터
            fallback_search_func: 캐시 미스 시 호출할 검색 함수
                async def search(query: str, category: str) -> List[Dict]
            similarity_threshold: 유사도 임계값

        Returns:
            FAQCacheResult: 검색 결과 (캐시 히트 여부 포함)
        """
        start_time = time.time()

        # 1. 캐시 검색
        cached = await self.search_cache(query, category, similarity_threshold)

        if cached:
            return cached

        # 2. 캐시 미스 - fallback 검색
        faqs = []
        if fallback_search_func:
            try:
                faqs = await fallback_search_func(query, category)
            except Exception as e:
                logger.error(f"Fallback search failed: {e}")

        search_time_ms = (time.time() - start_time) * 1000

        # 3. 결과 캐싱
        if faqs:
            await self.cache_result(query, faqs, category)

        return FAQCacheResult(
            query=query,
            faqs=faqs,
            cache_hit=False,
            similarity_score=0.0,
            cached_query="",
            search_time_ms=search_time_ms,
        )

    async def clear_cache(self, category: Optional[str] = None) -> int:
        """캐시를 초기화합니다.

        Args:
            category: 특정 카테고리만 삭제 (None이면 전체 삭제)

        Returns:
            int: 삭제된 행 수
        """
        if not self._initialized:
            return 0

        try:
            db = get_db_manager()

            if category:
                result = await db.execute(
                    f"DELETE FROM {CACHE_TABLE} WHERE category = $1",
                    category
                )
            else:
                result = await db.execute(f"DELETE FROM {CACHE_TABLE}")

            # 결과에서 삭제된 행 수 추출
            deleted = int(result.split()[-1]) if result else 0
            logger.info(f"Cache cleared: {deleted} entries removed")
            return deleted

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0

    async def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계를 반환합니다."""
        if not self._initialized:
            return {"initialized": False}

        try:
            db = get_db_manager()

            # 전체 캐시 수
            total = await db.fetchval(f"SELECT COUNT(*) FROM {CACHE_TABLE}")

            # 카테고리별 캐시 수
            category_stats = await db.fetch(f"""
                SELECT category, COUNT(*) as count, SUM(hit_count) as total_hits
                FROM {CACHE_TABLE}
                GROUP BY category
            """)

            return {
                "initialized": True,
                "total_cached_queries": total or 0,
                "similarity_threshold": SIMILARITY_THRESHOLD,
                "categories": [
                    {
                        "category": r["category"],
                        "count": r["count"],
                        "total_hits": r["total_hits"] or 0,
                    }
                    for r in category_stats
                ],
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"initialized": True, "error": str(e)}


# Singleton getter
def get_faq_cache() -> FAQSemanticCache:
    """FAQSemanticCache 싱글톤 인스턴스를 반환합니다."""
    return FAQSemanticCache()
