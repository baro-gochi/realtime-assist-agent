"""Agent 모듈 설정.

LangGraph 에이전트 관련 LLM 설정값.
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
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "150"))
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
# 싱글톤 인스턴스
# ============================================================

llm_config = LLMConfig()
agent_behavior_config = AgentBehaviorConfig()


# ============================================================
# 설정 로드 확인 로그
# ============================================================

logger.info(f"[Agent Config] .env 경로: {_env_path} (존재: {_env_path.exists()})")
logger.info(f"[Agent Config] LLM 모델: {llm_config.MODEL}")
logger.info(f"[Agent Config] Temperature: {llm_config.TEMPERATURE}")
logger.info(f"[Agent Config] Max Tokens: {llm_config.MAX_TOKENS}")
logger.info(f"[Agent Config] Reasoning Effort: {llm_config.REASONING_EFFORT}")
