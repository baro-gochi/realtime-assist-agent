"""상담 API 라우터 패키지.

상담 관련 API 엔드포인트를 제공합니다.
"""

from .consultation import router as consultation_router
from .comparison import router as comparison_router
from .faq import router as faq_router

__all__ = [
    "consultation_router",
    "comparison_router",
    "faq_router",
]
