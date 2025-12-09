"""LangGraph 에이전트 상태(State) 정의.

상담 지원 워크플로우에서 사용되는 상태 스키마를 정의합니다.

Usage:
    from modules.consultation import AgentState, create_initial_state
"""

from typing import List, TypedDict
from langchain_core.documents import Document


class AgentState(TypedDict):
    """상담원 Agent의 상태 스키마.

    LangGraph 워크플로우에서 노드 간 전달되는 데이터를 정의합니다.

    Attributes:
        summary (str):
            [입력] 상담 내용 요약
            사용자로부터 입력받은 원본 상담 요약 텍스트

        target_doc_name (str):
            [중간] 선택된 문서 별칭
            analyzer_node에서 결정된 검색 대상 문서

        search_query (str):
            [중간] 추출된 검색 키워드
            analyzer_node에서 추출된 핵심 키워드

        documents (List[Document]):
            [중간] 검색된 문서 리스트
            search_node에서 검색된 관련 문서들

        response_guide (str):
            [출력] 신입 상담원용 대응방안
            response_generator_node에서 생성된 최종 가이드 텍스트

        keyword_guide (str):
            [출력] 핵심 키워드 기반 간결 가이드
            keyword_guide_node에서 생성된 핵심 요점 텍스트

        faq_results (List[dict]):
            [출력] KT 멤버십 FAQ 검색 결과
            faq_search_node에서 검색된 관련 FAQ 리스트
    """

    # [입력] 상담 내용 요약
    summary: str

    # [중간] 선택된 문서 별칭 (또는 "없음")
    target_doc_name: str

    # [중간] 추출된 검색 키워드
    search_query: str

    # [중간] 검색된 문서 리스트
    documents: List[Document]

    # [출력] 신입 상담원용 대응방안
    response_guide: str

    # [출력] 핵심 키워드 기반 간결 가이드
    keyword_guide: str

    # [출력] KT 멤버십 FAQ 검색 결과
    faq_results: List[dict]


def create_initial_state(summary: str) -> dict:
    """초기 상태 생성.

    워크플로우 실행에 필요한 초기 상태를 생성합니다.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        dict: 초기 상태 딕셔너리
    """
    return {
        "summary": summary,
        "target_doc_name": "",
        "search_query": "",
        "documents": [],
        "response_guide": "",
        "keyword_guide": "",
        "faq_results": []
    }
