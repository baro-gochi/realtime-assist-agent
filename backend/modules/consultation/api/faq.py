"""KT 멤버십 FAQ API 라우터.

FAQ 검색 및 조회 API를 제공합니다:
1. FAQ 검색 (키워드 기반)
2. 카테고리별 FAQ 조회
3. 전체 FAQ 조회

엔드포인트:
    GET  /faq/search - FAQ 검색
    GET  /faq/categories - 카테고리 목록
    GET  /faq/category/{category} - 카테고리별 FAQ
    GET  /faq/all - 전체 FAQ
    POST /faq/reload - FAQ 데이터 리로드
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from modules.database import get_faq_service

logger = logging.getLogger(__name__)


class FAQItem(BaseModel):
    """FAQ 항목 모델."""
    id: str = Field(..., description="FAQ ID")
    category: str = Field(..., description="FAQ 카테고리")
    question: str = Field(..., description="질문")
    answer: str = Field(..., description="답변")


class FAQSearchResponse(BaseModel):
    """FAQ 검색 응답 모델."""
    query: str = Field(..., description="검색어")
    count: int = Field(..., description="결과 수")
    results: List[FAQItem] = Field(default_factory=list, description="검색 결과")
    processing_time_ms: float = Field(..., description="처리 시간 (ms)")


class FAQCategoriesResponse(BaseModel):
    """FAQ 카테고리 목록 응답 모델."""
    categories: List[str] = Field(default_factory=list, description="카테고리 목록")
    count: int = Field(..., description="카테고리 수")


class FAQAllResponse(BaseModel):
    """전체 FAQ 응답 모델."""
    total_count: int = Field(..., description="전체 FAQ 수")
    faqs: List[FAQItem] = Field(default_factory=list, description="FAQ 목록")


router = APIRouter(
    prefix="/faq",
    tags=["faq"],
    responses={
        500: {"description": "Server error"}
    }
)


@router.get(
    "/search",
    summary="FAQ 검색",
    description="키워드로 관련 FAQ를 검색합니다.",
    response_model=FAQSearchResponse,
)
async def search_faq(
    q: str = Query(..., min_length=1, description="검색어"),
    limit: int = Query(5, ge=1, le=20, description="최대 결과 수")
):
    """FAQ 검색.

    Args:
        q: 검색어 (필수)
        limit: 최대 결과 수 (기본: 5, 최대: 20)

    Returns:
        FAQSearchResponse: 검색 결과
    """
    start_time = time.perf_counter()

    try:
        faq_service = get_faq_service()

        if not faq_service.is_initialized:
            await faq_service.initialize()

        results = await faq_service.search(q, limit=limit)

        faq_items = [
            FAQItem(
                id=faq.get("id", ""),
                category=faq.get("category", ""),
                question=faq.get("question", ""),
                answer=faq.get("answer", "")
            )
            for faq in results
        ]

        processing_time_ms = (time.perf_counter() - start_time) * 1000

        logger.info(f"[FAQ API] Search '{q}' - {len(faq_items)} results in {processing_time_ms:.2f}ms")

        return FAQSearchResponse(
            query=q,
            count=len(faq_items),
            results=faq_items,
            processing_time_ms=round(processing_time_ms, 2)
        )

    except Exception as e:
        logger.error(f"[FAQ API] Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/categories",
    summary="FAQ 카테고리 목록",
    description="모든 FAQ 카테고리 목록을 반환합니다.",
    response_model=FAQCategoriesResponse,
)
async def get_categories():
    """FAQ 카테고리 목록 조회.

    Returns:
        FAQCategoriesResponse: 카테고리 목록
    """
    try:
        faq_service = get_faq_service()

        if not faq_service.is_initialized:
            await faq_service.initialize()

        categories = await faq_service.get_all_categories()

        return FAQCategoriesResponse(
            categories=categories,
            count=len(categories)
        )

    except Exception as e:
        logger.error(f"[FAQ API] Get categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/category/{category}",
    summary="카테고리별 FAQ 조회",
    description="특정 카테고리의 모든 FAQ를 반환합니다.",
    response_model=FAQAllResponse,
)
async def get_faq_by_category(category: str):
    """카테고리별 FAQ 조회.

    Args:
        category: 카테고리명

    Returns:
        FAQAllResponse: 해당 카테고리의 FAQ 목록
    """
    try:
        faq_service = get_faq_service()

        if not faq_service.is_initialized:
            await faq_service.initialize()

        faqs = await faq_service.get_by_category(category)

        faq_items = [
            FAQItem(
                id=faq.get("id", ""),
                category=faq.get("category", ""),
                question=faq.get("question", ""),
                answer=faq.get("answer", "")
            )
            for faq in faqs
        ]

        return FAQAllResponse(
            total_count=len(faq_items),
            faqs=faq_items
        )

    except Exception as e:
        logger.error(f"[FAQ API] Get by category error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/all",
    summary="전체 FAQ 조회",
    description="모든 FAQ를 반환합니다.",
    response_model=FAQAllResponse,
)
async def get_all_faqs():
    """전체 FAQ 조회.

    Returns:
        FAQAllResponse: 전체 FAQ 목록
    """
    try:
        faq_service = get_faq_service()

        if not faq_service.is_initialized:
            await faq_service.initialize()

        faqs = await faq_service.get_all()

        faq_items = [
            FAQItem(
                id=faq.get("id", ""),
                category=faq.get("category", ""),
                question=faq.get("question", ""),
                answer=faq.get("answer", "")
            )
            for faq in faqs
        ]

        return FAQAllResponse(
            total_count=len(faq_items),
            faqs=faq_items
        )

    except Exception as e:
        logger.error(f"[FAQ API] Get all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/reload",
    summary="FAQ 데이터 리로드",
    description="JSON 파일에서 FAQ 데이터를 다시 로드합니다.",
)
async def reload_faqs():
    """FAQ 데이터 리로드.

    Returns:
        dict: 리로드 결과
    """
    try:
        faq_service = get_faq_service()

        success = await faq_service.reload()

        if success:
            total = len(await faq_service.get_all())
            return {"status": "success", "message": f"FAQ reloaded: {total} items"}
        else:
            raise HTTPException(status_code=500, detail="FAQ reload failed")

    except Exception as e:
        logger.error(f"[FAQ API] Reload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
