"""LangGraph 에이전트 노드 정의.

상담 Agent의 핵심 노드들을 정의합니다:
1. analyzer_node: 상담 내용 분석 및 키워드 추출
2. search_node: 벡터 DB 하이브리드 검색
3. response_generator_node: 신입 상담원용 대응방안 생성
4. direct_embedding_search_node: 요약문 직접 임베딩 검색
5. keyword_guide_node: 핵심 키워드 기반 간결 가이드 생성
6. faq_search_node: KT 멤버십 FAQ 검색

Usage:
    from modules.consultation.nodes import analyzer_node, search_node, faq_search_node
"""

import logging
import time
from typing import List

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from modules.consultation.state import AgentState
from modules.consultation.config import consultation_settings
from modules.vector_db import get_vector_db_manager, get_doc_registry
from modules.database import get_faq_service

logger = logging.getLogger(__name__)


def analyzer_node(state: AgentState) -> dict:
    """[Node 1] 상담 내용 분석 및 키워드 추출.

    상담 요약 내용을 분석하여 핵심 키워드를 추출합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: target_doc_name, search_query
    """
    summary = state["summary"]
    logger.info(f"[Analyzer] 상담 내용 분석 시작: '{summary[:50]}...'")

    start_time = time.perf_counter()
    settings = consultation_settings

    # LLM 모델 초기화
    llm = ChatOpenAI(
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        max_tokens=50,
        streaming=False
    )

    # 키워드 추출 프롬프트
    prompt = ChatPromptTemplate.from_template("""
    아래 텍스트에서 상담/약관 검색에 필요한 핵심 키워드를 3~8개 추출하세요.

    규칙:
    - 약관/계약/요금/서비스 문맥에서 중요한 단어만 선택하세요.
    - 숫자 정보(개월 수, 약정 기간 등)는 반드시 포함하세요.
    - "해지/위약금/반환금" 계열 키워드 우선 가중치
    - 일반 단어(내용, 상세, 문의, 방식, 설명 등)는 제거하세요.
    - 출력은 공백으로 구분된 단어만 나열하세요.
    - 출력 형식: 키워드1 키워드2 키워드3 ...

    텍스트:
    {summary}
    """)

    # 체인 실행
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"summary": summary})

    # 결과 파싱
    try:
        target_name = "없음"
        query = response.strip()
    except Exception as e:
        logger.warning(f"[Analyzer] 파싱 실패, 원본 응답 사용: {e}")
        target_name = "없음"
        query = response

    duration = time.perf_counter() - start_time
    logger.info(f"[Analyzer] 완료 - 문서: [{target_name}], 키워드: [{query}], 소요시간: {duration:.3f}초")

    return {
        "target_doc_name": target_name,
        "search_query": query
    }


def search_node(state: AgentState) -> dict:
    """[Node 2] 하이브리드 검색 수행.

    추출된 키워드로 벡터 DB에서 관련 문서를 검색합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: documents
    """
    target_name = state["target_doc_name"]
    query = state["search_query"]

    logger.info(f"[Searcher] 검색 시작 - 문서: [{target_name}], 키워드: [{query}]")
    start_time = time.perf_counter()

    db_manager = get_vector_db_manager()
    doc_registry = get_doc_registry()

    docs = []

    # Scoped Search (타겟 문서 집중 검색)
    if target_name != "없음" and doc_registry.has_document(target_name):
        real_path = doc_registry.get_document_path(target_name)
        logger.info(f"[Searcher] Scoped 검색: '{target_name}' (k=2)")

        try:
            scoped_results = db_manager.similarity_search(
                query,
                k=2,
                filter_dict={"source": real_path}
            )
            docs.extend(scoped_results)
            logger.debug(f"[Searcher] Scoped 검색 결과: {len(scoped_results)}개")
        except Exception as e:
            logger.warning(f"[Searcher] Scoped 검색 오류: {e}")
    else:
        logger.info("[Searcher] Scoped 검색 스킵 (대상 문서 없음)")

    # Global Search (전체 범위 검색)
    logger.info("[Searcher] Global 검색 수행 (k=3)")
    try:
        global_results = db_manager.similarity_search(query, k=3)
        docs.extend(global_results)
        logger.debug(f"[Searcher] Global 검색 결과: {len(global_results)}개")
    except Exception as e:
        logger.error(f"[Searcher] Global 검색 오류: {e}")

    # 중복 제거
    unique_docs = []
    seen_content = set()

    for doc in docs:
        content_hash = doc.page_content[:50]
        if content_hash not in seen_content:
            unique_docs.append(doc)
            seen_content.add(content_hash)

    duration = time.perf_counter() - start_time
    logger.info(f"[Searcher] 완료 - {len(unique_docs)}개 문서 (중복 제거), 소요시간: {duration:.3f}초")

    return {"documents": unique_docs}


def response_generator_node(state: AgentState) -> dict:
    """[Node 3] 신입 상담원용 대응방안 생성.

    검색된 문서를 바탕으로 대응방안을 생성합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: response_guide
    """
    summary = state["summary"]
    documents = state["documents"]

    logger.info(f"[ResponseGen] 대응방안 생성 시작 - 참조 문서: {len(documents)}개")
    start_time = time.perf_counter()
    settings = consultation_settings

    # 컨텍스트 구성
    context_parts = []
    for i, doc in enumerate(documents):
        source_name = doc.metadata.get("source", "Unknown").split("/")[-1]
        page = doc.metadata.get("page", 0) + 1
        context_parts.append(
            f"[참고문서 {i+1}] {source_name} (p.{page})\n{doc.page_content}"
        )

    context = "\n\n".join(context_parts) if context_parts else "참고할 문서가 없습니다."

    # LLM 모델 초기화
    llm = ChatOpenAI(
        model=settings.RESPONSE_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.2,
        max_tokens=800,
        streaming=False
    )

    # 대응방안 생성 프롬프트
    prompt = ChatPromptTemplate.from_template("""
    신입 상담원 대응 가이드를 작성하세요.

    고객 문의 요약: {summary}
    관련 문서 내용: {context}

    요구 조건:
    - 문맥 기반으로 필요한 범위까지만 간결하게 확장하세요.
    - 고객 문의와 실제 문서 내용이 직접적으로 일치하지 않는 경우, "직접적 규정 없음"이라고 명시하세요.
    - 각 문서의 해당 조항에서 핵심 문구를 1~2줄로 요약해 제시하세요.
    - 문서에 없는 내용은 임의로 생성하지 마세요.
    - 서로 다른 문서에서 추출된 규정은 섞지 말고 문서별로 구분해 설명하세요.
    - 문장 톤은 상담원이 고객에게 설명하듯 부드럽고 명확하게 작성하세요.

    출력 형식:
    1. 안내 멘트
    2. 주의사항
    3. 확인 필요 사항
    4. 다음 단계 안내
    """)

    # 체인 실행
    chain = prompt | llm | StrOutputParser()
    response_guide = chain.invoke({
        "summary": summary,
        "context": context
    })

    duration = time.perf_counter() - start_time
    logger.info(f"[ResponseGen] 완료 - 응답 길이: {len(response_guide)}자, 소요시간: {duration:.3f}초")

    return {"response_guide": response_guide}


def direct_embedding_search_node(state: AgentState) -> dict:
    """[Node] 요약문 직접 임베딩 검색.

    키워드 추출 없이 요약문 자체를 임베딩하여 검색합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: documents
    """
    summary = state["summary"]

    logger.info(f"[DirectSearch] 직접 임베딩 검색 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    db_manager = get_vector_db_manager()

    try:
        docs = db_manager.similarity_search(summary, k=5)
        logger.debug(f"[DirectSearch] 검색 결과: {len(docs)}개 문서")
    except Exception as e:
        logger.error(f"[DirectSearch] 검색 오류: {e}")
        docs = []

    # 중복 제거
    unique_docs = []
    seen_content = set()

    for doc in docs:
        content_hash = doc.page_content[:50]
        if content_hash not in seen_content:
            unique_docs.append(doc)
            seen_content.add(content_hash)

    duration = time.perf_counter() - start_time
    logger.info(f"[DirectSearch] 완료 - {len(unique_docs)}개 문서, 소요시간: {duration:.3f}초")

    return {"documents": unique_docs}


def keyword_guide_node(state: AgentState) -> dict:
    """[Node] 핵심 키워드 기반 간결 가이드 생성.

    검색 결과를 바탕으로 핵심만 짧게 제시합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: keyword_guide
    """
    summary = state["summary"]
    documents = state["documents"]

    logger.info(f"[KeywordGuide] 핵심 가이드 생성 시작 - 참조 문서: {len(documents)}개")
    start_time = time.perf_counter()
    settings = consultation_settings

    # 컨텍스트 구성
    context_parts = []
    for i, doc in enumerate(documents):
        source_name = doc.metadata.get("source", "Unknown").split("/")[-1]
        page = doc.metadata.get("page", 0) + 1
        context_parts.append(
            f"[문서 {i+1}] {source_name} (p.{page})\n{doc.page_content}"
        )

    context = "\n\n".join(context_parts) if context_parts else "참고 문서 없음"

    # LLM 모델 초기화
    llm = ChatOpenAI(
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        max_tokens=300,
        streaming=False
    )

    # 핵심 키워드 가이드 프롬프트
    prompt = ChatPromptTemplate.from_template("""
상담원에게 필요한 핵심만 짧게 제시하세요.

고객 문의: {summary}
참고 문서: {context}

규칙:
- 긴 문장 금지. 핵심 키워드/요점만 나열
- 대화 순서에 맞게 정보 배치
- 상담원이 자신의 말로 정제할 수 있도록 핵심만 제공
- 각 항목은 한 줄 이내로 작성
- 문서에 없는 내용은 작성 금지

출력 형식:
* [주제] 핵심내용1. 핵심내용2. 핵심내용3.
* [다음주제] 핵심내용1. 핵심내용2.
...

예시:
* [요금제] 5G 스탠다드 월 69,000원. 데이터 무제한. 통화 무제한.
* [위약금] 24개월 약정. 잔여개월 x 할인액. 최대 300,000원.
* [확인사항] 가입일 확인 필요. 결합상품 여부 체크.
""")

    # 체인 실행
    chain = prompt | llm | StrOutputParser()
    keyword_guide = chain.invoke({
        "summary": summary,
        "context": context
    })

    duration = time.perf_counter() - start_time
    logger.info(f"[KeywordGuide] 완료 - 응답 길이: {len(keyword_guide)}자, 소요시간: {duration:.3f}초")

    return {"keyword_guide": keyword_guide}


async def faq_search_node(state: AgentState) -> dict:
    """[Node] KT 멤버십 FAQ 검색.

    상담 내용 또는 키워드로 관련 FAQ를 검색합니다.

    Args:
        state: 현재 상태

    Returns:
        dict: faq_results (list of FAQ dicts)
    """
    summary = state["summary"]
    search_query = state.get("search_query", "")

    # 검색 쿼리가 없으면 summary에서 키워드 추출
    query = search_query if search_query else summary

    logger.info(f"[FAQSearch] FAQ 검색 시작: '{query[:50]}...'")
    start_time = time.perf_counter()

    faq_service = get_faq_service()

    try:
        # FAQ 서비스 초기화 (첫 호출시)
        if not faq_service.is_initialized:
            await faq_service.initialize()

        # FAQ 검색 수행
        faq_results = await faq_service.search(query, limit=3)
        logger.debug(f"[FAQSearch] 검색 결과: {len(faq_results)}개 FAQ")

    except Exception as e:
        logger.error(f"[FAQSearch] 검색 오류: {e}")
        faq_results = []

    duration = time.perf_counter() - start_time
    logger.info(f"[FAQSearch] 완료 - {len(faq_results)}개 FAQ, 소요시간: {duration:.3f}초")

    return {"faq_results": faq_results}
