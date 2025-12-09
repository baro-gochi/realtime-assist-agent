"""Comparison API router.

Provides APIs for comparing different search/guide generation methods.

Endpoints:
    POST /comparison/direct-search       - Direct embedding search results
    POST /comparison/direct-keyword      - Direct embedding + keyword guide generation
    POST /comparison/keyword-extraction  - Keyword extraction + keyword guide generation
    POST /comparison/direct-full-guide   - Direct embedding + full guide generation

Comparison purpose:
    1. Compare direct embedding vs keyword extraction search quality
    2. Compare keyword guide vs full guide usefulness
"""

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException

from modules.consultation.models import (
    ComparisonRequest,
    DirectSearchResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse,
    DocumentInfo,
    ErrorResponse
)
from modules.consultation.workflow import (
    run_direct_search_async,
    run_direct_keyword_guide_async,
    run_keyword_extraction_guide_async,
    run_direct_full_guide_async
)
from modules.consultation.utils import request_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/comparison",
    tags=["comparison"],
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"}
    }
)


def _convert_documents(documents: list, max_docs: int) -> List[DocumentInfo]:
    """Convert document list to DocumentInfo list."""
    result = []
    for doc in documents[:max_docs]:
        content = doc.page_content
        result.append(DocumentInfo(
            source=doc.metadata.get("source", "Unknown").split("/")[-1],
            page=doc.metadata.get("page", 0) + 1,
            content=content[:500] + "..." if len(content) > 500 else content,
            score=None
        ))
    return result


@router.post(
    "/direct-search",
    summary="Direct embedding search results",
    description="""
    Directly embed the query and search for similar documents in vector DB.

    **Features:**
    - Embed summary directly without keyword extraction
    - Search only, no LLM API calls
    - Fast response time

    **Compare with:** /comparison/keyword-extraction (keyword extraction then search)
    """,
    response_model=DirectSearchResponse
)
async def direct_search(request: ComparisonRequest):
    """Direct embedding search API.

    Embeds the summary and searches for similar documents in vector DB.
    Fast response due to no keyword extraction process.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] Direct embedding search: '{request.summary[:50]}...'")

            try:
                result = await run_direct_search_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Direct embedding search failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during search: {str(e)}"
                )

            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = DirectSearchResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                total_results=len(result.get("documents", [])),
                documents=documents,
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] Direct embedding search completed: {len(documents)} docs, {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        raise


@router.post(
    "/direct-keyword",
    summary="Direct embedding + keyword guide generation",
    description="""
    Direct embedding search followed by concise keyword-based guide generation.

    **Workflow:**
    Summary -> Direct embedding search -> Keyword guide generation

    **Features:**
    - Skip keyword extraction (fast search)
    - Concise bullet points instead of long sentences
    - Easy for CS reps to paraphrase

    **Compare with:** /comparison/keyword-extraction (keyword extraction then search)
    """,
    response_model=KeywordGuideResponse
)
async def direct_keyword_guide(request: ComparisonRequest):
    """Direct embedding + keyword guide generation API.

    Embeds summary directly, searches, and generates concise keyword-based guide.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] Direct embedding + keyword guide: '{request.summary[:50]}...'")

            try:
                result = await run_direct_keyword_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Direct embedding + keyword guide failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during processing: {str(e)}"
                )

            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                extracted_keywords=None,
                documents=documents,
                keyword_guide=result.get("keyword_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] Direct embedding + keyword guide completed: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        raise


@router.post(
    "/keyword-extraction",
    summary="Keyword extraction + keyword guide generation",
    description="""
    Traditional keyword extraction followed by search and concise guide generation.

    **Workflow:**
    Summary -> Keyword extraction -> Vector search -> Keyword guide generation

    **Features:**
    - Extract keywords using existing analyzer_node
    - Search using existing search_node
    - Concise bullet points instead of long sentences

    **Compare with:** /comparison/direct-keyword (direct embedding search)
    """,
    response_model=KeywordGuideResponse
)
async def keyword_extraction_guide(request: ComparisonRequest):
    """Keyword extraction + keyword guide generation API.

    Uses traditional keyword extraction for search and generates keyword guide.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] Keyword extraction + keyword guide: '{request.summary[:50]}...'")

            try:
                result = await run_keyword_extraction_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Keyword extraction + keyword guide failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during processing: {str(e)}"
                )

            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method="keyword_extraction",
                extracted_keywords=result.get("search_query", ""),
                documents=documents,
                keyword_guide=result.get("keyword_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] Keyword extraction + keyword guide completed: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        raise


@router.post(
    "/direct-full-guide",
    summary="Direct embedding + full guide generation",
    description="""
    Direct embedding search followed by traditional sentence-style guide generation.

    **Workflow:**
    Summary -> Direct embedding search -> Full guide generation

    **Features:**
    - Skip keyword extraction (fast search)
    - Generate sentence-style guide using existing response_generator_node

    **Compare with:** /consultation/assist (keyword extraction + full guide)
    """,
    response_model=DirectFullGuideResponse
)
async def direct_full_guide(request: ComparisonRequest):
    """Direct embedding + full guide generation API.

    Embeds summary directly, searches, and generates traditional sentence-style guide.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] Direct embedding + full guide: '{request.summary[:50]}...'")

            try:
                result = await run_direct_full_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Direct embedding + full guide failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during processing: {str(e)}"
                )

            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = DirectFullGuideResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                documents=documents,
                response_guide=result.get("response_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] Direct embedding + full guide completed: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        raise
