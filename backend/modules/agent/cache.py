"""Redis LLM 캐싱 모듈.

OpenAI Rate Limit 방어 및 지연 시간 단축을 위한 LLM 응답 캐싱.

두 가지 캐싱 전략:
1. RedisSemanticCache: 유사 프롬프트 캐싱 (의미적 유사도 기반)
   - 임베딩을 사용하여 유사한 질문에 대해 캐시 히트
   - Rate Limit 방어에 효과적 (유사 질문 재사용)

2. RedisCache: 정확히 동일한 프롬프트 캐싱
   - 문자열 일치 기반으로 빠른 조회
   - 반복 질문에 효과적

OpenAI Implicit Prompt Caching:
    - 정적 접두사(System Message)를 동일하게 유지하면 OpenAI 백엔드에서 자동 캐싱
    - 이 모듈은 LangChain 레벨의 캐싱으로 API 호출 자체를 줄임
"""

import logging
from typing import Optional

from langchain_core.caches import BaseCache

from .config import redis_cache_config

logger = logging.getLogger(__name__)

# 글로벌 캐시 인스턴스 (싱글톤)
_llm_cache: Optional[BaseCache] = None
_cache_initialized: bool = False


def get_llm_cache() -> Optional[BaseCache]:
    """LLM 캐시 인스턴스를 반환합니다.

    Returns:
        BaseCache | None: 설정에 따른 캐시 인스턴스 또는 None (비활성화 시)
    """
    global _llm_cache, _cache_initialized

    if _cache_initialized:
        return _llm_cache

    _cache_initialized = True

    if not redis_cache_config.CACHE_ENABLED:
        logger.info("[LLM Cache] Caching disabled by configuration")
        return None

    try:
        if redis_cache_config.CACHE_TYPE == "semantic":
            _llm_cache = _create_semantic_cache()
        else:
            _llm_cache = _create_exact_cache()

        logger.info(
            f"[LLM Cache] Initialized: type={redis_cache_config.CACHE_TYPE}, "
            f"ttl={redis_cache_config.CACHE_TTL}s"
        )
        return _llm_cache

    except Exception as e:
        logger.warning(f"[LLM Cache] Failed to initialize: {e}. Continuing without cache.")
        return None


def _create_semantic_cache() -> BaseCache:
    """RedisSemanticCache 인스턴스를 생성합니다.

    유사 프롬프트에 대해 캐시 히트를 제공합니다.
    임베딩 모델을 사용하여 의미적 유사도를 계산합니다.
    """
    from langchain_redis import RedisSemanticCache
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    cache = RedisSemanticCache(
        redis_url=redis_cache_config.REDIS_URL,
        embeddings=embeddings,
        distance_threshold=redis_cache_config.SEMANTIC_DISTANCE_THRESHOLD,
        ttl=redis_cache_config.CACHE_TTL,
        name=redis_cache_config.CACHE_NAME,
    )

    logger.info(
        f"[LLM Cache] RedisSemanticCache created: "
        f"threshold={redis_cache_config.SEMANTIC_DISTANCE_THRESHOLD}"
    )
    return cache


def _create_exact_cache() -> BaseCache:
    """RedisCache 인스턴스를 생성합니다.

    정확히 동일한 프롬프트에 대해서만 캐시 히트를 제공합니다.
    """
    from langchain_redis import RedisCache

    cache = RedisCache(
        redis_url=redis_cache_config.REDIS_URL,
        ttl=redis_cache_config.CACHE_TTL,
    )

    logger.info("[LLM Cache] RedisCache (exact match) created")
    return cache


def setup_global_llm_cache() -> bool:
    """전역 LLM 캐시를 설정합니다.

    LangChain의 set_llm_cache를 사용하여 모든 LLM 호출에 캐싱을 적용합니다.

    Returns:
        bool: 캐시 설정 성공 여부
    """
    cache = get_llm_cache()

    if cache is None:
        return False

    try:
        from langchain_core.globals import set_llm_cache
        set_llm_cache(cache)
        logger.info("[LLM Cache] Global LLM cache activated")
        return True
    except Exception as e:
        logger.warning(f"[LLM Cache] Failed to set global cache: {e}")
        return False


def clear_llm_cache() -> bool:
    """LLM 캐시를 클리어합니다.

    Returns:
        bool: 클리어 성공 여부
    """
    cache = get_llm_cache()

    if cache is None:
        return False

    try:
        cache.clear()
        logger.info("[LLM Cache] Cache cleared")
        return True
    except Exception as e:
        logger.warning(f"[LLM Cache] Failed to clear cache: {e}")
        return False


def get_cache_stats() -> dict:
    """캐시 상태 정보를 반환합니다.

    Returns:
        dict: 캐시 설정 및 상태 정보
    """
    return {
        "enabled": redis_cache_config.CACHE_ENABLED,
        "type": redis_cache_config.CACHE_TYPE,
        "redis_url": redis_cache_config.REDIS_URL.split("@")[-1] if "@" in redis_cache_config.REDIS_URL else redis_cache_config.REDIS_URL,
        "ttl_seconds": redis_cache_config.CACHE_TTL,
        "semantic_threshold": redis_cache_config.SEMANTIC_DISTANCE_THRESHOLD if redis_cache_config.CACHE_TYPE == "semantic" else None,
        "cache_name": redis_cache_config.CACHE_NAME,
        "initialized": _cache_initialized,
        "cache_available": _llm_cache is not None,
    }
