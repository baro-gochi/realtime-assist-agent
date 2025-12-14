"""Agent 모듈 설정.

LangGraph 에이전트 관련 LLM 설정값 및 Redis 캐싱 설정.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# 환경변수 로드 (상위에서 이미 로드됨)
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_env_path = Path(__file__).parent.parent.parent / "config" / ".env"
load_dotenv(_env_path)


# ============================================================
# LLM 설정
# ============================================================

@dataclass
class LLMConfig:
    """LLM 모델 설정."""

    # 모델 식별자
    MODEL: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "openai:gpt-5-nano")
    )

    # OpenAI API 키
    OPENAI_API_KEY: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )

    # 모델 온도
    TEMPERATURE: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0"))
    )

    # 최대 토큰 수
    MAX_TOKENS: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "200"))
    )
    
    # 추론 노력 수준
    REASONING_EFFORT: Optional[str] = field(
        default_factory=lambda: os.getenv("REASONING_EFFORT")
    )

    @property
    def model_name(self) -> str:
        """모델 이름만 반환."""
        return self.MODEL.split(":")[-1] if ":" in self.MODEL else self.MODEL

# ============================================================
# 최종 요약 전용 LLM 설정
# ============================================================

@dataclass
class SummaryLLMConfig:
    """최종 요약 생성 전용 LLM 설정.

    세션 종료 시 구조화된 최종 요약을 생성하는 LLM 설정.
    실시간 분석용 LLM과 별도로 설정 가능.
    """

    # 모델 식별자 (기본값: 실시간 LLM과 동일)
    MODEL: str = field(
        default_factory=lambda: os.getenv("SUMMARY_LLM_MODEL", "openai:gpt-5-mini")
    )

    # 모델 온도 (요약은 일관성을 위해 낮은 온도 권장)
    TEMPERATURE: float = field(
        default_factory=lambda: float(os.getenv("SUMMARY_LLM_TEMPERATURE", "0"))
    )

    @property
    def model_name(self) -> str:
        """모델 이름만 반환."""
        return self.MODEL.split(":")[-1] if ":" in self.MODEL else self.MODEL


# ============================================================
# 에이전트 동작 설정
# ============================================================

@dataclass(frozen=True)
class AgentBehaviorConfig:
    """에이전트 동작 설정."""

    # 대화 컨텍스트 최대 메시지 수
    MAX_CONTEXT_MESSAGES: int = 20

    # 요약 생성 임계값 (이 메시지 수 초과 시 요약)
    SUMMARY_THRESHOLD: int = 15

    # 에이전트 응답 타임아웃 (초)
    RESPONSE_TIMEOUT: int = 30

    # 재시도 횟수
    MAX_RETRIES: int = 3

    # 재시도 간격 (초)
    RETRY_DELAY: float = 1.0


# ============================================================
# Redis LLM 캐싱 설정
# ============================================================

@dataclass
class RedisCacheConfig:
    """Redis LLM 캐싱 설정.

    OpenAI Rate Limit 방어 및 지연 시간 단축을 위한 캐싱 설정.
    - RedisSemanticCache: 유사 프롬프트 캐싱 (의미적 유사도 기반)
    - RedisCache: 정확히 동일한 프롬프트 캐싱 (문자열 일치)

    OpenAI Implicit Prompt Caching:
    - 정적 접두사(System Message)를 동일하게 유지하면 OpenAI 백엔드에서 자동 캐싱
    - Time-to-First-Token 감소 및 비용 절감 효과
    """

    # Redis 연결 URL
    REDIS_URL: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379")
    )

    # 캐시 활성화 여부
    CACHE_ENABLED: bool = field(
        default_factory=lambda: os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
    )

    # 캐시 타입: "semantic" (유사도 기반) 또는 "exact" (정확 일치)
    CACHE_TYPE: str = field(
        default_factory=lambda: os.getenv("LLM_CACHE_TYPE", "semantic")
    )

    # 캐시 TTL (초) - 기본 1시간
    CACHE_TTL: int = field(
        default_factory=lambda: int(os.getenv("LLM_CACHE_TTL", "3600"))
    )

    # 시맨틱 캐시 유사도 임계값 (0~1, 낮을수록 엄격)
    # 0.1 = 매우 유사한 프롬프트만 캐시 히트
    # 0.2 = 적당히 유사한 프롬프트도 캐시 히트
    SEMANTIC_DISTANCE_THRESHOLD: float = field(
        default_factory=lambda: float(os.getenv("LLM_CACHE_DISTANCE_THRESHOLD", "0.15"))
    )

    # 캐시 인덱스 이름 (Redis key prefix)
    CACHE_NAME: str = field(
        default_factory=lambda: os.getenv("LLM_CACHE_NAME", "kt_agent_llm_cache")
    )


# ============================================================
# 싱글톤 인스턴스
# ============================================================

llm_config = LLMConfig()
summary_llm_config = SummaryLLMConfig()
agent_behavior_config = AgentBehaviorConfig()
redis_cache_config = RedisCacheConfig()


# ============================================================
# 설정 로드 확인 로그
# ============================================================

logger.info(f"[Agent Config] .env 경로: {_env_path} (존재: {_env_path.exists()})")
logger.info(f"[Agent Config] LLM 모델: {llm_config.MODEL}")
logger.info(f"[Agent Config] Temperature: {llm_config.TEMPERATURE}")
logger.info(f"[Agent Config] Max Tokens: {llm_config.MAX_TOKENS}")
logger.info(f"[Agent Config] Reasoning Effort: {llm_config.REASONING_EFFORT}")
logger.info(f"[Agent Config] Summary LLM 모델: {summary_llm_config.MODEL}")
logger.info(f"[Agent Config] Summary Temperature: {summary_llm_config.TEMPERATURE}")
logger.info(f"[Agent Config] Redis Cache Enabled: {redis_cache_config.CACHE_ENABLED}")
logger.info(f"[Agent Config] Redis Cache Type: {redis_cache_config.CACHE_TYPE}")
