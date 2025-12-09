"""상담 지원 모듈 설정.

ChromaDB, OpenAI 모델, Rate Limiting 등 상담 RAG 에이전트 설정.
"""

import os
import logging
from typing import Optional
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# .env 파일 로드
_env_path = Path(__file__).parent.parent.parent / "config" / ".env"
load_dotenv(_env_path)


class ConsultationSettings(BaseSettings):
    """상담 지원 모듈 설정 클래스.

    환경 변수를 Python 객체로 매핑하고 유효성을 검증합니다.
    """

    # OpenAI API 설정
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API 키"
    )

    # ChromaDB 설정 (마이그레이션 후 제거 예정)
    CHROMA_DB_PATH: str = Field(
        default="",
        description="ChromaDB 저장 경로 (Deprecated: pgvector로 이전)"
    )

    CHROMA_COLLECTION_NAME: str = Field(
        default="kt_terms",
        description="ChromaDB 컬렉션 이름 (Deprecated: pgvector로 이전)"
    )

    # PostgreSQL pgvector 설정
    DATABASE_URL: str = Field(
        default="postgresql://assistant:assistant123@localhost:5432/realtime_assist",
        description="PostgreSQL 연결 문자열 (pgvector)"
    )

    PGVECTOR_COLLECTION_NAME: str = Field(
        default="aicc_documents",
        description="pgvector 컬렉션 이름"
    )

    # 임베딩 모델 설정
    EMBEDDING_MODEL_NAME: str = Field(
        default="text-embedding-3-large",
        description="OpenAI 임베딩 모델명 (3072차원)"
    )

    EMBEDDING_DEVICE: str = Field(
        default="cpu",
        description="임베딩 모델 실행 디바이스"
    )

    # LLM 모델 설정
    ANALYZER_MODEL: str = Field(
        default="gpt-4o-mini",
        description="키워드 추출용 LLM 모델",
        validation_alias="CONSULTATION_ANALYZER_MODEL"
    )

    RESPONSE_MODEL: str = Field(
        default="gpt-4o-mini",
        description="응답 생성용 LLM 모델",
        validation_alias="CONSULTATION_RESPONSE_MODEL"
    )

    # Rate Limiting 설정
    MAX_CONCURRENT_REQUESTS: int = Field(
        default=10,
        description="최대 동시 요청 수",
        validation_alias="CONSULTATION_MAX_CONCURRENT_REQUESTS"
    )

    REQUEST_TIMEOUT: int = Field(
        default=60,
        description="요청당 타임아웃 (초)",
        validation_alias="CONSULTATION_REQUEST_TIMEOUT"
    )

    RATE_LIMIT_PER_MINUTE: int = Field(
        default=30,
        description="분당 최대 요청 수",
        validation_alias="CONSULTATION_RATE_LIMIT_PER_MINUTE"
    )

    # 문서 레지스트리 설정
    DOC_REGISTRY_PATH: Optional[str] = Field(
        default=None,
        description="문서 매핑 JSON 파일 경로",
        validation_alias="CONSULTATION_DOC_REGISTRY_PATH"
    )

    # 로깅 설정
    LOG_LEVEL: str = Field(
        default="INFO",
        description="로그 레벨"
    )

    @field_validator('EMBEDDING_DEVICE')
    @classmethod
    def validate_device(cls, v: str) -> str:
        """임베딩 디바이스 유효성 검증"""
        allowed = ['cpu', 'cuda']
        if v.lower() not in allowed:
            raise ValueError(f"EMBEDDING_DEVICE는 {allowed} 중 하나여야 합니다.")
        return v.lower()

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """로그 레벨 유효성 검증"""
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL은 {allowed} 중 하나여야 합니다.")
        return v.upper()

    class Config:
        """Pydantic 설정"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_consultation_settings() -> ConsultationSettings:
    """설정 싱글톤 인스턴스 반환.

    Returns:
        ConsultationSettings: 설정 객체
    """
    return ConsultationSettings()


# 전역 settings 객체
consultation_settings = get_consultation_settings()

# 로그 출력
logger.info(f"[Consultation Config] .env 경로: {_env_path} (존재: {_env_path.exists()})")
logger.info(f"[Consultation Config] Analyzer 모델: {consultation_settings.ANALYZER_MODEL}")
logger.info(f"[Consultation Config] Response 모델: {consultation_settings.RESPONSE_MODEL}")
logger.info(f"[Consultation Config] pgvector 컬렉션: {consultation_settings.PGVECTOR_COLLECTION_NAME}")
