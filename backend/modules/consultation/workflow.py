"""LangGraph 워크플로우 구성.

상담 지원 Agent의 워크플로우를 구성하고 실행합니다.

Usage:
    from modules.consultation import run_consultation

    result = run_consultation("인터넷 해지 문의")
    print(result["response_guide"])
"""

import logging
import asyncio
from typing import Dict, Any
from functools import lru_cache

from langgraph.graph import StateGraph, START, END

from modules.consultation.state import AgentState, create_initial_state
from modules.consultation.nodes import (
    analyzer_node,
    search_node,
    response_generator_node,
    direct_embedding_search_node,
    keyword_guide_node
)

logger = logging.getLogger(__name__)

def build_workflow() -> StateGraph:
    """LangGraph 워크플로우 구성.

    워크플로우 구조:
        [START] -> [analyzer] -> [searcher] -> [response_generator] -> [END]
    """
    logger.info("LangGraph 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("response_generator", response_generator_node)

    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "searcher")
    workflow.add_edge("searcher", "response_generator")
    workflow.add_edge("response_generator", END)

    logger.info("워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_agent_app():
    """컴파일된 Agent 애플리케이션 반환 (싱글톤)."""
    logger.info("Agent 애플리케이션 컴파일 중...")
    workflow = build_workflow()
    app = workflow.compile()
    logger.info("Agent 애플리케이션 컴파일 완료")
    return app


def run_consultation(summary: str) -> Dict[str, Any]:
    """상담 Agent 실행.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        Dict: 워크플로우 실행 결과
    """
    logger.info(f"상담 Agent 실행: '{summary[:50]}...'")

    app = get_agent_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("상담 Agent 실행 완료")
        return result
    except Exception as e:
        logger.error(f"상담 Agent 실행 실패: {e}")
        raise


async def run_consultation_async(summary: str) -> Dict[str, Any]:
    """상담 Agent 비동기 실행."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_consultation, summary)
    return result


def reset_agent_app() -> None:
    """Agent 앱 캐시 초기화."""
    logger.warning("Agent 앱 캐시 초기화")
    get_agent_app.cache_clear()


# ==========================================
# 직접 임베딩 검색 워크플로우
# ==========================================

def build_direct_search_workflow() -> StateGraph:
    """직접 임베딩 검색 워크플로우 구성.

    워크플로우 구조:
        [START] -> [direct_searcher] -> [END]
    """
    logger.info("직접 임베딩 검색 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("direct_searcher", direct_embedding_search_node)

    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", END)

    logger.info("직접 임베딩 검색 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_search_app():
    """직접 임베딩 검색 Agent 애플리케이션 반환 (싱글톤)."""
    logger.info("직접 임베딩 검색 Agent 컴파일 중...")
    workflow = build_direct_search_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 검색 Agent 컴파일 완료")
    return app


def run_direct_search(summary: str) -> Dict[str, Any]:
    """직접 임베딩 검색 실행."""
    logger.info(f"직접 임베딩 검색 실행: '{summary[:50]}...'")

    app = get_direct_search_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 검색 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 검색 실행 실패: {e}")
        raise


async def run_direct_search_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 검색 비동기 실행."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_search, summary)
    return result


# ==========================================
# 직접 임베딩 + 핵심 가이드 워크플로우
# ==========================================

def build_direct_keyword_guide_workflow() -> StateGraph:
    """직접 임베딩 검색 + 핵심 가이드 워크플로우 구성.

    워크플로우 구조:
        [START] -> [direct_searcher] -> [keyword_guide] -> [END]
    """
    logger.info("직접 임베딩 + 핵심 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("direct_searcher", direct_embedding_search_node)
    workflow.add_node("keyword_guide", keyword_guide_node)

    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", "keyword_guide")
    workflow.add_edge("keyword_guide", END)

    logger.info("직접 임베딩 + 핵심 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_keyword_guide_app():
    """직접 임베딩 + 핵심 가이드 Agent 애플리케이션 반환 (싱글톤)."""
    logger.info("직접 임베딩 + 핵심 가이드 Agent 컴파일 중...")
    workflow = build_direct_keyword_guide_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 + 핵심 가이드 Agent 컴파일 완료")
    return app


def run_direct_keyword_guide(summary: str) -> Dict[str, Any]:
    """직접 임베딩 검색 + 핵심 가이드 생성 실행."""
    logger.info(f"직접 임베딩 + 핵심 가이드 실행: '{summary[:50]}...'")

    app = get_direct_keyword_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 + 핵심 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 + 핵심 가이드 실행 실패: {e}")
        raise


async def run_direct_keyword_guide_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 + 핵심 가이드 비동기 실행."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_keyword_guide, summary)
    return result


# ==========================================
# 키워드 추출 + 핵심 가이드 워크플로우
# ==========================================

def build_keyword_extraction_guide_workflow() -> StateGraph:
    """키워드 추출 + 검색 + 핵심 가이드 워크플로우 구성.

    워크플로우 구조:
        [START] -> [analyzer] -> [searcher] -> [keyword_guide] -> [END]
    """
    logger.info("키워드 추출 + 핵심 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("keyword_guide", keyword_guide_node)

    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "searcher")
    workflow.add_edge("searcher", "keyword_guide")
    workflow.add_edge("keyword_guide", END)

    logger.info("키워드 추출 + 핵심 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_keyword_extraction_guide_app():
    """키워드 추출 + 핵심 가이드 Agent 애플리케이션 반환 (싱글톤)."""
    logger.info("키워드 추출 + 핵심 가이드 Agent 컴파일 중...")
    workflow = build_keyword_extraction_guide_workflow()
    app = workflow.compile()
    logger.info("키워드 추출 + 핵심 가이드 Agent 컴파일 완료")
    return app


def run_keyword_extraction_guide(summary: str) -> Dict[str, Any]:
    """키워드 추출 + 검색 + 핵심 가이드 생성 실행."""
    logger.info(f"키워드 추출 + 핵심 가이드 실행: '{summary[:50]}...'")

    app = get_keyword_extraction_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("키워드 추출 + 핵심 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"키워드 추출 + 핵심 가이드 실행 실패: {e}")
        raise


async def run_keyword_extraction_guide_async(summary: str) -> Dict[str, Any]:
    """키워드 추출 + 핵심 가이드 비동기 실행."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_keyword_extraction_guide, summary)
    return result


# ==========================================
# 직접 임베딩 + 긴 가이드 워크플로우
# ==========================================

def build_direct_full_guide_workflow() -> StateGraph:
    """직접 임베딩 검색 + 긴 가이드 워크플로우 구성.

    워크플로우 구조:
        [START] -> [direct_searcher] -> [response_generator] -> [END]
    """
    logger.info("직접 임베딩 + 긴 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("direct_searcher", direct_embedding_search_node)
    workflow.add_node("response_generator", response_generator_node)

    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", "response_generator")
    workflow.add_edge("response_generator", END)

    logger.info("직접 임베딩 + 긴 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_full_guide_app():
    """직접 임베딩 + 긴 가이드 Agent 애플리케이션 반환 (싱글톤)."""
    logger.info("직접 임베딩 + 긴 가이드 Agent 컴파일 중...")
    workflow = build_direct_full_guide_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 + 긴 가이드 Agent 컴파일 완료")
    return app


def run_direct_full_guide(summary: str) -> Dict[str, Any]:
    """직접 임베딩 검색 + 긴 가이드 생성 실행."""
    logger.info(f"직접 임베딩 + 긴 가이드 실행: '{summary[:50]}...'")

    app = get_direct_full_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 + 긴 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 + 긴 가이드 실행 실패: {e}")
        raise


async def run_direct_full_guide_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 + 긴 가이드 비동기 실행."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_full_guide, summary)
    return result
