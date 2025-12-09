"""벡터 데이터베이스 연결 및 관리 모듈.

PostgreSQL pgvector 벡터 스토어의 연결과 검색을 담당합니다.

Usage:
    from modules.vector_db import get_vector_db_manager

    db_manager = get_vector_db_manager()
    results = db_manager.similarity_search("검색 키워드", k=3)
"""

import logging
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from modules.consultation.config import consultation_settings

logger = logging.getLogger(__name__)


class VectorDBManager:
    """벡터 데이터베이스 관리 클래스.

    PostgreSQL pgvector와의 연결을 관리하고 검색 기능을 제공합니다.
    싱글톤 패턴으로 구현되어 있어 애플리케이션 전체에서
    하나의 인스턴스만 사용됩니다.

    Attributes:
        embedding_model: OpenAI 임베딩 모델
        vectorstore: PGVector 벡터 스토어 인스턴스
        is_initialized: 초기화 완료 여부
    """

    def __init__(self):
        """VectorDBManager 초기화.

        실제 DB 연결은 initialize() 메서드에서 수행됩니다.
        """
        self.embedding_model = None
        self.vectorstore = None
        self.is_initialized = False
        logger.info("VectorDBManager 인스턴스 생성됨 (아직 초기화 안됨)")

    def _get_connection_string(self) -> str:
        """psycopg 호환 연결 문자열 생성.

        LangChain PGVector는 postgresql+psycopg:// 형식을 요구합니다.
        """
        url = consultation_settings.DATABASE_URL

        # postgresql:// -> postgresql+psycopg:// 변환
        if url.startswith("postgresql://") and "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)

        return url

    def initialize(self) -> None:
        """벡터 DB 연결 초기화.

        임베딩 모델을 로드하고 pgvector에 연결합니다.

        Raises:
            RuntimeError: DB 연결 실패 시
        """
        if self.is_initialized:
            logger.debug("이미 초기화됨 - 스킵")
            return

        settings = consultation_settings

        # 설정 검증
        if not settings.DATABASE_URL:
            logger.warning("DATABASE_URL이 설정되지 않음 - VectorDB 비활성화")
            return

        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY가 설정되지 않음 - VectorDB 비활성화")
            return

        try:
            logger.info("벡터 DB 초기화 시작...")

            # 임베딩 모델 로드
            logger.info(f"임베딩 모델 로딩 중: {settings.EMBEDDING_MODEL_NAME}")
            self.embedding_model = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL_NAME,
                openai_api_key=settings.OPENAI_API_KEY
            )
            logger.info("임베딩 모델 로딩 완료")

            # pgvector 연결
            connection_string = self._get_connection_string()
            logger.info(f"pgvector 연결 중: {connection_string.split('@')[0]}@***")

            self.vectorstore = PGVector(
                embeddings=self.embedding_model,
                collection_name=settings.PGVECTOR_COLLECTION_NAME,
                connection=connection_string,
                use_jsonb=True,
            )
            logger.info(f"pgvector 연결 완료 (컬렉션: {settings.PGVECTOR_COLLECTION_NAME})")

            self.is_initialized = True
            logger.info("벡터 DB 초기화 완료")

        except Exception as e:
            logger.error(f"벡터 DB 초기화 실패: {str(e)}")
            raise RuntimeError(f"벡터 DB 초기화 실패: {str(e)}")

    def ensure_initialized(self) -> None:
        """초기화 상태 확인 및 필요시 초기화 수행."""
        if not self.is_initialized:
            self.initialize()

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """유사도 기반 문서 검색.

        Args:
            query: 검색 쿼리 텍스트
            k: 반환할 문서 수 (기본값: 3)
            filter_dict: 메타데이터 필터 조건

        Returns:
            List[Document]: 유사도 순으로 정렬된 문서 리스트

        Raises:
            RuntimeError: 검색 실패 시
        """
        self.ensure_initialized()

        if not self.vectorstore:
            logger.warning("VectorDB가 초기화되지 않음 - 빈 결과 반환")
            return []

        try:
            logger.debug(f"검색 수행: query='{query[:50]}...', k={k}, filter={filter_dict}")

            if filter_dict:
                results = self.vectorstore.similarity_search(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search(query, k=k)

            logger.debug(f"검색 완료: {len(results)}개 문서 반환")
            return results

        except Exception as e:
            logger.error(f"검색 실패: {str(e)}")
            raise RuntimeError(f"벡터 검색 실패: {str(e)}")

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """유사도 점수와 함께 문서 검색.

        Args:
            query: 검색 쿼리 텍스트
            k: 반환할 문서 수
            filter_dict: 메타데이터 필터 조건

        Returns:
            List[tuple]: (Document, score) 튜플 리스트
        """
        self.ensure_initialized()

        if not self.vectorstore:
            return []

        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(query, k=k)

            return results

        except Exception as e:
            logger.error(f"검색(with score) 실패: {str(e)}")
            raise RuntimeError(f"벡터 검색 실패: {str(e)}")

    def get_collection_info(self) -> Dict[str, Any]:
        """컬렉션 정보 조회.

        Returns:
            Dict: 컬렉션 정보
        """
        self.ensure_initialized()

        settings = consultation_settings

        if not self.vectorstore:
            return {
                "collection_name": settings.PGVECTOR_COLLECTION_NAME,
                "is_initialized": False,
                "error": "VectorDB not initialized"
            }

        try:
            # pgvector는 직접 카운트 쿼리 필요
            from sqlalchemy import create_engine, text

            connection_string = self._get_connection_string()
            engine = create_engine(connection_string)

            with engine.connect() as conn:
                # 컬렉션 UUID 조회
                result = conn.execute(
                    text("SELECT uuid FROM langchain_pg_collection WHERE name = :name"),
                    {"name": settings.PGVECTOR_COLLECTION_NAME}
                )
                row = result.fetchone()

                if row:
                    collection_uuid = str(row[0])
                    # 문서 수 조회
                    count_result = conn.execute(
                        text("SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = :uuid"),
                        {"uuid": collection_uuid}
                    )
                    count = count_result.fetchone()[0]
                else:
                    count = 0

            return {
                "collection_name": settings.PGVECTOR_COLLECTION_NAME,
                "database_url": settings.DATABASE_URL.split("@")[0] + "@***",
                "document_count": count,
                "is_initialized": self.is_initialized,
                "embedding_model": settings.EMBEDDING_MODEL_NAME,
                "backend": "pgvector"
            }

        except Exception as e:
            logger.error(f"컬렉션 정보 조회 실패: {str(e)}")
            return {
                "collection_name": settings.PGVECTOR_COLLECTION_NAME,
                "is_initialized": self.is_initialized,
                "error": str(e),
                "backend": "pgvector"
            }

    def health_check(self) -> bool:
        """DB 연결 상태 확인.

        Returns:
            bool: 정상이면 True
        """
        try:
            self.ensure_initialized()
            if not self.vectorstore:
                return False
            self.vectorstore.similarity_search("test", k=1)
            return True
        except Exception as e:
            logger.error(f"Health check 실패: {str(e)}")
            return False


# 싱글톤 인스턴스 관리
_vector_db_manager: Optional[VectorDBManager] = None


def get_vector_db_manager() -> VectorDBManager:
    """VectorDBManager 싱글톤 인스턴스 반환.

    Returns:
        VectorDBManager: DB 매니저 인스턴스
    """
    global _vector_db_manager

    if _vector_db_manager is None:
        _vector_db_manager = VectorDBManager()

    return _vector_db_manager


def reset_vector_db_manager() -> None:
    """DB 매니저 인스턴스 리셋."""
    global _vector_db_manager
    logger.warning("VectorDBManager 리셋 수행")
    _vector_db_manager = None
