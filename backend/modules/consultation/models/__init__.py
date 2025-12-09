"""상담 API 모델 패키지.

FastAPI 엔드포인트의 요청/응답 스키마를 제공합니다.
"""

from .schemas import (
    # 공통
    DocumentInfo,
    HealthStatus,
    ErrorResponse,
    QueueStatusResponse,
    # 신입 상담원용
    ConsultationRequest,
    ConsultationResponse,
    # 비교용
    ComparisonRequest,
    DirectSearchResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse,
)

__all__ = [
    "DocumentInfo",
    "HealthStatus",
    "ErrorResponse",
    "QueueStatusResponse",
    "ConsultationRequest",
    "ConsultationResponse",
    "ComparisonRequest",
    "DirectSearchResponse",
    "KeywordGuideResponse",
    "DirectFullGuideResponse",
]
