"""API 요청/응답 스키마 정의.

FastAPI 엔드포인트의 입출력 데이터 모델을 정의합니다.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==========================================
# 공통 모델
# ==========================================

class DocumentInfo(BaseModel):
    """검색된 문서 정보."""
    source: str = Field(
        ...,
        description="문서 파일 경로/이름",
        json_schema_extra={"example": "인터넷서비스이용약관.pdf"}
    )
    page: int = Field(
        default=1,
        description="페이지 번호",
        json_schema_extra={"example": 5}
    )
    content: str = Field(
        ...,
        description="문서 내용",
        json_schema_extra={"example": "제15조(해지) 1. 이용자가 서비스를 해지하고자 할 경우..."}
    )
    score: Optional[float] = Field(
        default=None,
        description="유사도 점수",
        json_schema_extra={"example": 0.234}
    )


class HealthStatus(BaseModel):
    """서비스 상태 정보."""
    status: str = Field(
        ...,
        description="전체 상태 (healthy/unhealthy)",
        json_schema_extra={"example": "healthy"}
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="체크 시간"
    )
    components: Dict[str, Any] = Field(
        default_factory=dict,
        description="개별 컴포넌트 상태"
    )


class ErrorResponse(BaseModel):
    """에러 응답 모델."""
    error: str = Field(
        ...,
        description="에러 타입",
        json_schema_extra={"example": "ValidationError"}
    )
    message: str = Field(
        ...,
        description="에러 메시지",
        json_schema_extra={"example": "summary 필드는 필수입니다."}
    )
    detail: Optional[Dict[str, Any]] = Field(
        default=None,
        description="상세 에러 정보"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="에러 발생 시간"
    )


class QueueStatusResponse(BaseModel):
    """대기열 상태 응답."""
    current_requests: int = Field(..., description="현재 처리 중인 요청 수")
    max_requests: int = Field(..., description="최대 동시 요청 수")
    queue_length: int = Field(..., description="대기 중인 요청 수")
    is_accepting: bool = Field(..., description="새 요청 수락 가능 여부")


# ==========================================
# 신입 상담원용 API 모델
# ==========================================

class ConsultationRequest(BaseModel):
    """신입 상담원용 상담 요청."""
    summary: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="상담 내용 요약",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    include_documents: bool = Field(
        default=True,
        description="응답에 참조 문서 포함 여부"
    )
    max_documents: int = Field(
        default=3,
        ge=1,
        le=10,
        description="검색할 최대 문서 수"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 발생하는 위약금 문의.",
                    "include_documents": True,
                    "max_documents": 3
                }
            ]
        }
    }


class ConsultationResponse(BaseModel):
    """신입 상담원용 상담 응답."""
    original_summary: str = Field(..., description="원본 상담 요약")
    extracted_keywords: str = Field(
        ...,
        description="추출된 검색 키워드",
        json_schema_extra={"example": "약정 해지 위약금 계산"}
    )
    target_document: str = Field(
        ...,
        description="선택된 대상 문서",
        json_schema_extra={"example": "인터넷이용약관"}
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    response_guide: str = Field(
        ...,
        description="신입 상담원을 위한 대응방안",
        json_schema_extra={"example": "고객님께 다음과 같이 안내해 주세요..."}
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )


# ==========================================
# 비교용 API 모델
# ==========================================

class ComparisonRequest(BaseModel):
    """비교용 API 공통 요청 모델."""
    summary: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="상담 내용 요약",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    include_documents: bool = Field(
        default=True,
        description="응답에 참조 문서 포함 여부"
    )
    max_documents: int = Field(
        default=5,
        ge=1,
        le=10,
        description="반환할 최대 문서 수"
    )


class DirectSearchResponse(BaseModel):
    """직접 임베딩 검색 결과 응답."""
    original_summary: str = Field(..., description="원본 상담 요약")
    search_method: str = Field(
        default="direct_embedding",
        description="검색 방식"
    )
    total_results: int = Field(..., description="검색된 문서 수")
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )


class KeywordGuideResponse(BaseModel):
    """핵심 키워드 가이드 응답."""
    original_summary: str = Field(..., description="원본 상담 요약")
    search_method: str = Field(
        ...,
        description="검색 방식 (direct_embedding / keyword_extraction)"
    )
    extracted_keywords: Optional[str] = Field(
        default=None,
        description="추출된 검색 키워드 (keyword_extraction 방식에서만)"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    keyword_guide: str = Field(
        ...,
        description="핵심 키워드 기반 간결 가이드"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )


class DirectFullGuideResponse(BaseModel):
    """직접 임베딩 + 긴 가이드 응답."""
    original_summary: str = Field(..., description="원본 상담 요약")
    search_method: str = Field(
        default="direct_embedding",
        description="검색 방식"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    response_guide: str = Field(
        ...,
        description="신입 상담원을 위한 대응방안 (문장형)"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )
