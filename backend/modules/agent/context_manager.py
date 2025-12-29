"""RoomAgent Context Manager - LLM 컨텍스트 관리 계층.

OpenAI Implicit Caching 최적화를 위한 시스템 메시지 및 고객 컨텍스트 관리.
Single Responsibility 원칙에 따라 컨텍스트 관련 로직을 분리합니다.

Caching Strategy:
    - 정적 시스템 메시지를 동일하게 유지하여 TTFT(Time To First Token) 감소
    - 고객 정보가 변경될 때만 컨텍스트 업데이트
    - 동일한 고객 정보에 대해 동일한 문자열 생성 보장
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# 기본 시스템 메시지 (모든 에이전트 공통)
DEFAULT_BASE_SYSTEM_MESSAGE = """고객 상담 대화를 분석하여 요약하세요."""


class RoomAgentContextManager:
    """RoomAgent의 LLM 컨텍스트를 관리하는 클래스.

    OpenAI Implicit Caching을 위해 정적 시스템 메시지를 관리하고,
    고객 정보 기반 컨텍스트 생성을 담당합니다.

    Attributes:
        room_name: 방 이름
        _base_system_message: 기본 시스템 메시지 (불변)
        static_system_prefix: 현재 활성화된 정적 접두사 (고객 컨텍스트 포함)
        system_message: 하위 호환성을 위한 별칭
    """

    def __init__(
        self,
        room_name: str,
        base_system_message: str = None
    ):
        """ContextManager 초기화.

        Args:
            room_name: 방 이름
            base_system_message: 기본 시스템 메시지 (None이면 기본값 사용)
        """
        self.room_name = room_name
        self._base_system_message = base_system_message or DEFAULT_BASE_SYSTEM_MESSAGE
        self.static_system_prefix = self._base_system_message
        self.system_message = self._base_system_message

        logger.debug(
            f"[ContextManager] 초기화 완료 - room={room_name}, "
            f"base_message_len={len(self._base_system_message)}"
        )

    def reset(self):
        """컨텍스트를 초기 상태로 리셋합니다.

        고객 정보가 포함된 컨텍스트를 기본 시스템 메시지로 초기화합니다.
        세션 종료 시 또는 새로운 고객 연결 전에 호출됩니다.
        """
        self.static_system_prefix = self._base_system_message
        self.system_message = self._base_system_message
        logger.debug(f"[ContextManager] 컨텍스트 초기화: {self.room_name}")

    def set_customer_context(
        self,
        customer_info: Dict[str, Any],
        consultation_history: List[Dict[str, Any]]
    ) -> None:
        """고객 정보를 컨텍스트에 설정합니다.

        OpenAI Implicit Caching 최적화:
        - 고객 정보가 변경될 때만 static_system_prefix를 업데이트
        - 동일한 고객 정보면 캐시가 유지됨

        Args:
            customer_info: DB에서 조회한 고객 정보
            consultation_history: 고객의 과거 상담 이력
        """
        if not customer_info:
            logger.warning(f"[ContextManager] 고객 정보 없음: {self.room_name}")
            return

        if not self._base_system_message:
            logger.warning(f"[ContextManager] 기본 시스템 메시지 없음: {self.room_name}")
            return

        customer_context = self._generate_customer_context(
            customer_info,
            consultation_history
        )

        # 정적 접두사 업데이트 (OpenAI Implicit Caching 대상)
        self.static_system_prefix = self._base_system_message + customer_context
        self.system_message = self.static_system_prefix

        logger.info(
            f"[ContextManager] 고객 컨텍스트 설정: {self.room_name} - "
            f"{customer_info.get('customer_name')} ({len(self.static_system_prefix)}자)"
        )

    def _generate_customer_context(
        self,
        customer_info: Dict[str, Any],
        consultation_history: List[Dict[str, Any]]
    ) -> str:
        """고객 컨텍스트 문자열을 생성합니다.

        Note:
            이 문자열은 OpenAI Implicit Caching의 키로 사용되므로,
            동일한 고객 정보에 대해 정확히 동일한 문자열이 생성되어야 합니다.

        Args:
            customer_info: 고객 정보
            consultation_history: 상담 이력

        Returns:
            고객 컨텍스트 문자열
        """
        customer_context = f"""

현재 상담 고객 정보:
- 이름: {customer_info.get('customer_name', '알 수 없음')}
- 등급: {customer_info.get('membership_grade', '알 수 없음')}
- 요금제: {customer_info.get('current_plan', '알 수 없음')}
- 월정액: {customer_info.get('monthly_fee', 0):,}원
- 약정상태: {customer_info.get('contract_status', '알 수 없음')}
- 결합정보: {customer_info.get('bundle_info', '없음')}
"""
        if consultation_history:
            customer_context += "\n최근 상담 이력:\n"
            for idx, history in enumerate(consultation_history[:3], 1):
                date = history.get('consultation_date', '')
                ctype = history.get('consultation_type', '')
                detail = history.get('detail', {})
                summary = detail.get('summary', '') if isinstance(detail, dict) else str(detail)
                customer_context += f"  {idx}. [{date}] {ctype}: {summary}\n"

        return customer_context

    def get_graph_context(self) -> Dict[str, str]:
        """LangGraph 실행을 위한 컨텍스트 딕셔너리를 반환합니다.

        Returns:
            LangGraph context 파라미터에 전달할 딕셔너리
        """
        return {
            "static_system_prefix": self.static_system_prefix,
            "system_message": self.system_message,
        }

    @property
    def base_system_message(self) -> str:
        """기본 시스템 메시지 (읽기 전용)."""
        return self._base_system_message

    @property
    def is_customer_context_set(self) -> bool:
        """고객 컨텍스트가 설정되어 있는지 확인합니다."""
        return self.static_system_prefix != self._base_system_message

    def __repr__(self) -> str:
        return (
            f"RoomAgentContextManager(room={self.room_name}, "
            f"customer_context={self.is_customer_context_set})"
        )
