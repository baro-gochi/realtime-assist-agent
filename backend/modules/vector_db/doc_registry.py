"""문서 레지스트리 관리 모듈.

상담에 사용되는 문서들의 매핑 정보를 관리합니다.

Usage:
    from modules.vector_db import get_doc_registry

    registry = get_doc_registry()
    path = registry.get_document_path("인터넷이용약관")
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

from modules.consultation.config import consultation_settings

logger = logging.getLogger(__name__)


# 기본 문서 레지스트리
DEFAULT_DOC_REGISTRY: Dict[str, str] = {
    "인터넷이용약관": "/content/(이용약관전문)인터넷서비스이용약관_202509.pdf",
}


class DocumentRegistry:
    """문서 레지스트리 관리 클래스.

    문서 별칭과 실제 파일 경로 간의 매핑을 관리합니다.

    Attributes:
        registry: 문서 별칭 -> 경로 매핑 딕셔너리
        source: 레지스트리 소스
    """

    def __init__(self):
        """DocumentRegistry 초기화."""
        self.registry: Dict[str, str] = {}
        self.source: str = "default"
        self._load_registry()

    def _load_registry(self) -> None:
        """레지스트리 로딩."""
        settings = consultation_settings
        if settings.DOC_REGISTRY_PATH:
            self._load_from_json(settings.DOC_REGISTRY_PATH)
        else:
            self._load_default()

    def _load_default(self) -> None:
        """기본 레지스트리 로딩."""
        self.registry = DEFAULT_DOC_REGISTRY.copy()
        self.source = "default"
        logger.info(f"기본 문서 레지스트리 로딩 완료: {len(self.registry)}개 문서")

    def _load_from_json(self, json_path: str) -> None:
        """JSON 파일에서 레지스트리 로딩.

        Args:
            json_path: JSON 파일 경로
        """
        try:
            path = Path(json_path)

            if not path.exists():
                logger.warning(f"JSON 파일 없음: {json_path}, 기본 레지스트리 사용")
                self._load_default()
                return

            with open(path, 'r', encoding='utf-8') as f:
                self.registry = json.load(f)

            self.source = json_path
            logger.info(f"JSON에서 문서 레지스트리 로딩 완료: {len(self.registry)}개 문서")

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}, 기본 레지스트리 사용")
            self._load_default()
        except Exception as e:
            logger.error(f"레지스트리 로딩 실패: {e}, 기본 레지스트리 사용")
            self._load_default()

    def get_document_path(self, doc_name: str) -> Optional[str]:
        """문서 별칭으로 실제 경로 조회.

        Args:
            doc_name: 문서 별칭

        Returns:
            str: 실제 파일 경로, 없으면 None
        """
        return self.registry.get(doc_name)

    def has_document(self, doc_name: str) -> bool:
        """문서 존재 여부 확인.

        Args:
            doc_name: 문서 별칭

        Returns:
            bool: 존재하면 True
        """
        return doc_name in self.registry

    def get_all_document_names(self) -> List[str]:
        """모든 문서 별칭 목록 반환.

        Returns:
            List[str]: 문서 별칭 리스트
        """
        return list(self.registry.keys())

    def get_document_list_string(self) -> str:
        """문서 목록을 문자열로 반환 (프롬프트용).

        Returns:
            str: 줄바꿈으로 구분된 문서 목록
        """
        return "\n".join([f"- {name}" for name in self.registry.keys()])

    def get_registry_info(self) -> Dict:
        """레지스트리 정보 조회.

        Returns:
            Dict: 레지스트리 메타 정보
        """
        return {
            "source": self.source,
            "document_count": len(self.registry),
            "documents": self.get_all_document_names()
        }

    def reload(self) -> None:
        """레지스트리 재로딩."""
        logger.info("문서 레지스트리 재로딩 중...")
        self._load_registry()


# 싱글톤 인스턴스 관리
_doc_registry: Optional[DocumentRegistry] = None


def get_doc_registry() -> DocumentRegistry:
    """DocumentRegistry 싱글톤 인스턴스 반환.

    Returns:
        DocumentRegistry: 레지스트리 인스턴스
    """
    global _doc_registry

    if _doc_registry is None:
        _doc_registry = DocumentRegistry()

    return _doc_registry


def reset_doc_registry() -> None:
    """레지스트리 인스턴스 리셋."""
    global _doc_registry
    logger.info("DocumentRegistry 리셋")
    _doc_registry = None
