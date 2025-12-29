"""RoomAgent Repository - DB 영속성 계층.

RoomAgent의 세션, 전사, 에이전트 결과 저장을 담당하는 Repository입니다.
Single Responsibility 원칙에 따라 DB 관련 로직을 분리합니다.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

logger = logging.getLogger(__name__)

# Database repositories (lazy import to avoid circular dependencies)
_session_repo = None
_transcript_repo = None
_agent_result_repo = None


def _get_db_repositories():
    """DB Repository 싱글톤 인스턴스들을 반환합니다 (lazy initialization)."""
    global _session_repo, _transcript_repo, _agent_result_repo
    if _session_repo is None:
        from modules.database import (
            get_session_repository,
            get_transcript_repository,
            get_agent_result_repository,
        )
        _session_repo = get_session_repository()
        _transcript_repo = get_transcript_repository()
        _agent_result_repo = get_agent_result_repository()
    return _session_repo, _transcript_repo, _agent_result_repo


class RoomAgentRepository:
    """RoomAgent의 DB 영속성을 담당하는 Repository.

    세션 관리, 전사 저장, 에이전트 결과 저장 등
    모든 DB 관련 작업을 캡슐화합니다.

    Attributes:
        room_name: 방 이름
        session_id: 현재 세션 ID
        save_to_db: DB 저장 활성화 여부
        _turn_index: 전사 순서 인덱스
    """

    def __init__(self, room_name: str, save_to_db: bool = True):
        """Repository 초기화.

        Args:
            room_name: 방 이름
            save_to_db: DB 저장 활성화 여부
        """
        self.room_name = room_name
        self.save_to_db = save_to_db
        self.session_id: Optional[UUID] = None
        self._turn_index = 0

    def reset(self):
        """Repository 상태를 초기화합니다."""
        self.session_id = None
        self._turn_index = 0

    async def create_session(
        self,
        agent_name: str,
        room_id: UUID = None,
        customer_id: int = None,
        agent_id: str = None,
        channel: str = "call",
        metadata: dict = None
    ) -> Optional[UUID]:
        """새로운 상담 세션을 생성합니다.

        Args:
            agent_name: 상담사 이름
            room_id: WebRTC 룸 ID
            customer_id: 고객 ID
            agent_id: 상담사 ID
            channel: 채널 (call, chat)
            metadata: 추가 메타데이터

        Returns:
            생성된 세션 UUID 또는 None
        """
        logger.info(
            f"[Repository] 세션 생성 요청 - room={self.room_name}, "
            f"agent={agent_name}, room_id={room_id}"
        )

        if not self.save_to_db:
            logger.warning(f"[Repository] 세션 생성 스킵: save_to_db=False")
            return None

        session_repo, _, _ = _get_db_repositories()

        self.session_id = await session_repo.create_session(
            agent_name=agent_name,
            room_id=room_id,
            customer_id=customer_id,
            agent_id=agent_id,
            channel=channel,
            metadata=metadata or {"room_name": self.room_name}
        )

        if self.session_id:
            self._turn_index = 0
            logger.info(f"[Repository] 세션 생성 성공 - session_id={self.session_id}")
        else:
            logger.error(f"[Repository] 세션 생성 실패 - room={self.room_name}")

        return self.session_id

    async def end_session(
        self,
        final_summary: str = None,
        consultation_type: str = None
    ) -> bool:
        """상담 세션을 종료합니다.

        Args:
            final_summary: 최종 요약
            consultation_type: 상담 유형

        Returns:
            성공 여부
        """
        logger.info(
            f"[Repository] 세션 종료 요청 - room={self.room_name}, "
            f"session_id={self.session_id}"
        )

        if not self.save_to_db:
            logger.warning(f"[Repository] 세션 종료 스킵: save_to_db=False")
            return False

        if not self.session_id:
            logger.warning(f"[Repository] 세션 종료 스킵: session_id가 None")
            return False

        session_repo, _, _ = _get_db_repositories()

        logger.info(f"[Repository] 세션 종료 DB 저장 중 - session={self.session_id}")
        success = await session_repo.end_session(
            session_id=self.session_id,
            final_summary=final_summary,
            consultation_type=consultation_type
        )

        if success:
            logger.info(f"[Repository] 세션 종료 성공 - session_id={self.session_id}")
        else:
            logger.error(f"[Repository] 세션 종료 실패 - session_id={self.session_id}")

        return success

    async def update_session_customer(self, customer_id: int) -> bool:
        """세션에 고객 정보를 연결합니다.

        Args:
            customer_id: 고객 ID

        Returns:
            성공 여부
        """
        if not self.save_to_db or not self.session_id:
            return False

        session_repo, _, _ = _get_db_repositories()
        return await session_repo.update_customer(self.session_id, customer_id)

    async def save_transcript(
        self,
        speaker_type: str,
        speaker_name: str,
        text: str,
        timestamp: datetime,
        confidence: float = None
    ) -> bool:
        """전사 내용을 DB에 저장합니다.

        Args:
            speaker_type: 발화자 타입 (agent, customer)
            speaker_name: 발화자 이름
            text: 발화 내용
            timestamp: 발화 시간
            confidence: STT 신뢰도

        Returns:
            성공 여부
        """
        logger.debug(
            f"[Repository] 전사 저장 시도 - save_to_db={self.save_to_db}, "
            f"session_id={self.session_id}"
        )

        if not self.save_to_db:
            logger.debug("[Repository] 전사 저장 스킵: save_to_db=False")
            return False

        if not self.session_id:
            logger.warning(f"[Repository] 전사 저장 스킵: session_id가 None")
            return False

        _, transcript_repo, _ = _get_db_repositories()

        self._turn_index += 1
        logger.info(
            f"[Repository] 전사 저장 중 - session={self.session_id}, "
            f"turn={self._turn_index}, speaker={speaker_name}"
        )

        result = await transcript_repo.add_transcript(
            session_id=self.session_id,
            turn_index=self._turn_index,
            speaker_type=speaker_type,
            speaker_name=speaker_name,
            text=text,
            timestamp=timestamp,
            confidence=confidence
        )

        if result:
            logger.info(f"[Repository] 전사 저장 완료 - turn={self._turn_index}")
        else:
            logger.error(f"[Repository] 전사 저장 실패 - turn={self._turn_index}")

        return result

    async def save_agent_results(
        self,
        turn_id: str,
        intent_result: dict = None,
        sentiment_result: dict = None,
        summary_result: dict = None,
        rag_result: dict = None,
        faq_result: dict = None,
        risk_result: dict = None
    ):
        """에이전트 분석 결과를 DB에 저장합니다.

        Args:
            turn_id: 연관된 turn ID
            intent_result: 의도 분석 결과
            sentiment_result: 감정 분석 결과
            summary_result: 요약 결과
            rag_result: RAG 검색 결과
            faq_result: FAQ 검색 결과
            risk_result: 리스크 분석 결과
        """
        result_types = []
        if intent_result:
            result_types.append("intent")
        if sentiment_result:
            result_types.append("sentiment")
        if summary_result:
            result_types.append("summary")
        if rag_result:
            result_types.append("rag")
        if faq_result:
            result_types.append("faq")
        if risk_result:
            result_types.append("risk")

        logger.debug(
            f"[Repository] 결과 저장 시도 - save_to_db={self.save_to_db}, "
            f"session_id={self.session_id}, types={result_types}"
        )

        if not self.save_to_db:
            logger.debug("[Repository] 결과 저장 스킵: save_to_db=False")
            return

        if not self.session_id:
            logger.warning(f"[Repository] 결과 저장 스킵: session_id가 None")
            return

        logger.info(
            f"[Repository] 결과 저장 시작 - session={self.session_id}, "
            f"types={result_types}"
        )

        _, _, agent_result_repo = _get_db_repositories()

        # 각 결과 타입별로 저장
        results_to_save = [
            ("intent", intent_result),
            ("sentiment", sentiment_result),
            ("summary", summary_result),
            ("rag", rag_result),
            ("faq", faq_result),
            ("risk", risk_result),
        ]

        for result_type, result_data in results_to_save:
            if result_data:
                await agent_result_repo.save_result(
                    session_id=self.session_id,
                    result_type=result_type,
                    result_data=result_data,
                    turn_id=turn_id
                )
