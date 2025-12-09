"""Vector DB 모듈.

ChromaDB 벡터 스토어 연결과 문서 레지스트리 관리를 제공합니다.

Classes:
    VectorDBManager: ChromaDB 벡터 스토어 관리
    DocumentRegistry: 문서 별칭-경로 매핑 관리

Functions:
    get_vector_db_manager: VectorDBManager 싱글톤 반환
    get_doc_registry: DocumentRegistry 싱글톤 반환
"""

from .manager import VectorDBManager, get_vector_db_manager, reset_vector_db_manager
from .doc_registry import DocumentRegistry, get_doc_registry, reset_doc_registry

__all__ = [
    "VectorDBManager",
    "get_vector_db_manager",
    "reset_vector_db_manager",
    "DocumentRegistry",
    "get_doc_registry",
    "reset_doc_registry",
]
