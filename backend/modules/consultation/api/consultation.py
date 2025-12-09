"""신입 상담원용 API 라우터.

상담 내용을 입력받아 다음을 수행합니다:
1. 키워드 추출
2. 관련 문서 검색
3. 대응방안 생성

엔드포인트:
    POST /consultation/assist - 상담 지원 요청
"""

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException

from modules.consultation.models import (
    ConsultationRequest,
    ConsultationResponse,
    DocumentInfo,
    ErrorResponse
)
from modules.consultation.workflow import run_consultation_async
from modules.consultation.utils import request_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/consultation",
    tags=["consultation"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"}
    }
)


@router.post(
    "/assist",
    summary="Consultation assist request",
    description="""
    Consultation support API for new CS representatives.

    Process:
    1. AI analyzes the consultation content and extracts keywords
    2. Searches internal regulations/terms documents
    3. Generates response guidelines

    **Rate Limit**: 30 requests/minute
    **Concurrent requests**: max 10
    """,
    response_model=ConsultationResponse,
    responses={
        200: {
            "description": "Successfully processed",
            "content": {
                "application/json": {
                    "example": {
                        "original_summary": "Internet contract termination penalty inquiry",
                        "extracted_keywords": "Internet contract termination penalty",
                        "target_document": "None",
                        "documents": [],
                        "response_guide": "Please provide the following guidance to the customer...",
                        "processing_time_ms": 1234.5
                    }
                }
            }
        }
    }
)
async def assist_consultation(request: ConsultationRequest):
    """Process consultation assist request.

    Args:
        request: Consultation request info
            - summary: Consultation summary (required)
            - include_documents: Include documents in response (default: True)
            - max_documents: Maximum documents to return (default: 3)

    Returns:
        ConsultationResponse: Consultation assist result

    Raises:
        HTTPException(429): Rate limit exceeded
        HTTPException(500): Processing error
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] Consultation assist request: '{request.summary[:50]}...'")

            try:
                result = await run_consultation_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Agent execution failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during consultation processing: {str(e)}"
                )

            documents: List[DocumentInfo] = []
            if request.include_documents and result.get("documents"):
                for doc in result["documents"][:request.max_documents]:
                    documents.append(DocumentInfo(
                        source=doc.metadata.get("source", "Unknown").split("/")[-1],
                        page=doc.metadata.get("page", 0) + 1,
                        content=doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                        score=None
                    ))

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = ConsultationResponse(
                original_summary=request.summary,
                extracted_keywords=result.get("search_query", ""),
                target_document=result.get("target_doc_name", "None"),
                documents=documents,
                response_guide=result.get("response_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] Consultation assist completed: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            logger.warning("[API] Rate limit exceeded")
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        raise

    except TimeoutError:
        logger.error("[API] Request timeout")
        raise HTTPException(
            status_code=503,
            detail="Server is busy. Please try again later."
        )
