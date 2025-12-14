"""FAQ Semantic Cache 테스트 스크립트 (pgvector).

사용법:
    cd backend
    uv run python test/test_faq_semantic_cache.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "config" / ".env")


async def test_semantic_cache():
    """FAQ Semantic Cache 테스트."""
    from modules.database import (
        get_db_manager,
        get_faq_service,
        get_faq_cache,
    )

    print("=" * 60)
    print("FAQ Semantic Cache Test (pgvector)")
    print("=" * 60)

    # 1. DB 초기화
    print("\n[1] Database 초기화...")
    db = get_db_manager()
    if not await db.initialize():
        print("Database 연결 실패!")
        return

    # 2. FAQ Service 초기화
    print("\n[2] FAQ Service 초기화...")
    faq_service = get_faq_service()
    if not await faq_service.initialize():
        print("FAQ Service 초기화 실패!")
        return

    print(f"   - 로드된 FAQ: {len(faq_service._faqs)}개")

    # 3. FAQ Cache 초기화
    print("\n[3] FAQ Cache 초기화 (pgvector)...")
    faq_cache = get_faq_cache()
    if not await faq_cache.initialize():
        print("FAQ Cache 초기화 실패!")
        return

    # 4. 캐시 통계 (초기)
    stats = await faq_cache.get_cache_stats()
    print(f"   - 초기 캐시 상태: {stats.get('total_cached_queries', 0)}개 캐시됨")

    # 5. 테스트 쿼리들
    test_queries = [
        ("VIP 등급이 되려면 어떻게 해야 해요?", "등급"),
        ("VIP 조건이 뭐예요?", "등급"),  # 유사한 질문 - 캐시 히트 예상
        ("VVIP 되는 방법 알려주세요", "등급"),  # 유사한 질문
        ("영화 예매 할인 받으려면 어떻게 해요?", "멤버십 혜택"),
        ("영화관 할인 방법이요", "멤버십 혜택"),  # 유사한 질문
        ("멤버십 포인트는 얼마나 받을 수 있나요?", "등급"),
        ("포인트 잔액 확인하고 싶어요", "등급"),  # 유사한 질문
    ]

    print("\n[4] Semantic Search 테스트")
    print("-" * 60)

    for query, category in test_queries:
        result = await faq_service.semantic_search(
            query=query,
            category=category,
            limit=3,
            distance_threshold=0.45,  # 0.45 similarity 이상이면 캐시 히트 (한국어 의미 매칭)
        )

        cache_status = "HIT" if result.cache_hit else "MISS"
        print(f"\nQuery: '{query}'")
        print(f"  Category: {category}")
        print(f"  Cache: {cache_status} (similarity={result.similarity_score:.3f})")
        print(f"  Time: {result.search_time_ms:.2f}ms")
        print(f"  Results: {len(result.faqs)}개")

        if result.cache_hit and result.cached_query:
            print(f"  Cached Query: '{result.cached_query[:50]}...'")

        if result.faqs:
            print(f"  Top FAQ: {result.faqs[0].get('question', '')[:50]}...")

    # 6. 캐시 통계 (업데이트 후)
    print("\n" + "=" * 60)
    print("[5] 최종 캐시 통계")
    stats = await faq_cache.get_cache_stats()
    print(f"   - 총 캐시된 쿼리: {stats.get('total_cached_queries', 0)}개")
    print(f"   - 유사도 임계값: {stats.get('similarity_threshold', 'N/A')}")
    if stats.get("categories"):
        for cat in stats["categories"]:
            print(f"   - {cat['category']}: {cat['count']}개, 히트 {cat['total_hits']}회")

    # 7. 정리
    print("\n[6] 정리 중...")
    await db.close()
    print("완료!")


async def test_cache_clear():
    """캐시 초기화 테스트."""
    from modules.database import get_db_manager, get_faq_cache

    print("\n" + "=" * 60)
    print("Cache Clear Test")
    print("=" * 60)

    db = get_db_manager()
    await db.initialize()

    cache = get_faq_cache()
    await cache.initialize()

    deleted = await cache.clear_cache()
    print(f"   - 삭제된 캐시: {deleted}개")

    await db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        asyncio.run(test_cache_clear())
    else:
        asyncio.run(test_semantic_cache())
