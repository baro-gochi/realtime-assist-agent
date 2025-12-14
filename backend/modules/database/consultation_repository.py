"""상담 세션 레포지토리 모듈.

상담 세션, 통화 전사, 에이전트 결과에 대한 CRUD 작업을 제공합니다.

Classes:
    ConsultationSessionRepository: 상담 세션 관리
    ConsultationTranscriptRepository: 통화 전사 관리
    ConsultationAgentResultRepository: 에이전트 결과 관리
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from .connection import get_db_manager

logger = logging.getLogger(__name__)


class ConsultationSessionRepository:
    """상담 세션 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

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
            room_id: WebRTC 룸 ID (선택)
            customer_id: 고객 ID (선택)
            agent_id: 상담사 ID (선택)
            channel: 채널 (call, chat)
            metadata: 추가 메타데이터

        Returns:
            생성된 세션의 UUID 또는 None
        """
        if not self.db.is_initialized:
            logger.warning("Database not initialized, skipping session creation")
            return None

        try:
            metadata_json = json.dumps(metadata or {})

            session_id = await self.db.fetchval(
                """
                INSERT INTO consultation_sessions
                (room_id, customer_id, agent_id, agent_name, channel, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING session_id
                """,
                room_id, customer_id, agent_id, agent_name, channel, metadata_json
            )
            logger.info(f"Created consultation session: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create consultation session: {e}")
            return None

    async def update_customer(
        self,
        session_id: UUID,
        customer_id: int
    ) -> bool:
        """세션에 고객 정보를 연결합니다.

        Args:
            session_id: 세션 UUID
            customer_id: 고객 ID

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                UPDATE consultation_sessions
                SET customer_id = $2
                WHERE session_id = $1
                """,
                session_id, customer_id
            )
            logger.info(f"Updated session {session_id} with customer_id {customer_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update customer for session {session_id}: {e}")
            return False

    async def end_session(
        self,
        session_id: UUID,
        final_summary: str = None,
        consultation_type: str = None
    ) -> bool:
        """상담 세션을 종료합니다.

        Args:
            session_id: 세션 UUID
            final_summary: 최종 요약
            consultation_type: 상담 유형

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            result = await self.db.fetchval(
                "SELECT end_consultation_session($1, $2, $3)",
                session_id, final_summary, consultation_type
            )
            if result:
                logger.info(f"Ended consultation session: {session_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {e}")
            return False

    async def get_session(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """세션 정보를 조회합니다.

        Args:
            session_id: 세션 UUID

        Returns:
            세션 정보 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                """
                SELECT
                    cs.*,
                    c.customer_name,
                    c.phone_number,
                    c.membership_grade
                FROM consultation_sessions cs
                LEFT JOIN customers c ON cs.customer_id = c.customer_id
                WHERE cs.session_id = $1
                """,
                session_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def get_session_by_room(self, room_id: UUID) -> Optional[Dict[str, Any]]:
        """룸 ID로 세션을 조회합니다.

        Args:
            room_id: 룸 UUID

        Returns:
            세션 정보 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                """
                SELECT * FROM consultation_sessions
                WHERE room_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                room_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get session by room {room_id}: {e}")
            return None

    async def get_customer_sessions(
        self,
        customer_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """고객의 상담 세션 목록을 조회합니다.

        Args:
            customer_id: 고객 ID
            limit: 조회 개수 제한

        Returns:
            세션 목록
        """
        if not self.db.is_initialized:
            return []

        try:
            rows = await self.db.fetch(
                """
                SELECT * FROM consultation_session_summary
                WHERE customer_id = $1
                ORDER BY started_at DESC
                LIMIT $2
                """,
                customer_id, limit
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get sessions for customer {customer_id}: {e}")
            return []

    async def get_recent_sessions(
        self,
        status: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """최근 상담 세션 목록을 조회합니다.

        Args:
            status: 상태 필터 (선택)
            limit: 조회 개수 제한

        Returns:
            세션 목록
        """
        if not self.db.is_initialized:
            return []

        try:
            if status:
                rows = await self.db.fetch(
                    """
                    SELECT * FROM consultation_session_summary
                    WHERE status = $1
                    ORDER BY started_at DESC
                    LIMIT $2
                    """,
                    status, limit
                )
            else:
                rows = await self.db.fetch(
                    """
                    SELECT * FROM consultation_session_summary
                    ORDER BY started_at DESC
                    LIMIT $1
                    """,
                    limit
                )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {e}")
            return []


class ConsultationTranscriptRepository:
    """통화 전사 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

    async def add_transcript(
        self,
        session_id: UUID,
        turn_index: int,
        speaker_type: str,
        text: str,
        timestamp: datetime,
        speaker_name: str = None,
        confidence: float = None,
        is_final: bool = True,
        source: str = "google"
    ) -> bool:
        """통화 전사를 저장합니다.

        Args:
            session_id: 세션 UUID
            turn_index: 발화 순서
            speaker_type: 발화자 타입 (agent, customer)
            text: 발화 내용
            timestamp: 발화 시간
            speaker_name: 발화자 이름 (선택)
            confidence: STT 신뢰도 (선택)
            is_final: 최종 결과 여부
            source: STT 소스

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                INSERT INTO consultation_transcripts
                (session_id, turn_index, speaker_type, speaker_name, text, timestamp, confidence, is_final, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (session_id, turn_index) DO UPDATE
                SET text = EXCLUDED.text, confidence = EXCLUDED.confidence, is_final = EXCLUDED.is_final
                """,
                session_id, turn_index, speaker_type, speaker_name, text, timestamp, confidence, is_final, source
            )
            logger.debug(f"Saved transcript turn {turn_index} for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
            return False

    async def add_transcripts_batch(
        self,
        session_id: UUID,
        transcripts: List[Dict[str, Any]]
    ) -> int:
        """여러 전사를 일괄 저장합니다.

        Args:
            session_id: 세션 UUID
            transcripts: 전사 목록 [{turn_index, speaker_type, text, timestamp, ...}, ...]

        Returns:
            저장된 개수
        """
        if not self.db.is_initialized:
            return 0

        saved_count = 0
        for t in transcripts:
            success = await self.add_transcript(
                session_id=session_id,
                turn_index=t.get("turn_index"),
                speaker_type=t.get("speaker_type"),
                text=t.get("text"),
                timestamp=t.get("timestamp"),
                speaker_name=t.get("speaker_name"),
                confidence=t.get("confidence"),
                is_final=t.get("is_final", True),
                source=t.get("source", "google")
            )
            if success:
                saved_count += 1

        logger.info(f"Batch saved {saved_count}/{len(transcripts)} transcripts for session {session_id}")
        return saved_count

    async def get_session_transcripts(
        self,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """세션의 전사 목록을 조회합니다.

        Args:
            session_id: 세션 UUID
            limit: 조회 개수 제한
            offset: 시작 위치

        Returns:
            전사 목록
        """
        if not self.db.is_initialized:
            return []

        try:
            rows = await self.db.fetch(
                """
                SELECT turn_index, speaker_type, speaker_name, text, timestamp, confidence, source
                FROM consultation_transcripts
                WHERE session_id = $1
                ORDER BY turn_index ASC
                LIMIT $2 OFFSET $3
                """,
                session_id, limit, offset
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get transcripts for session {session_id}: {e}")
            return []

    async def get_conversation_text(self, session_id: UUID) -> str:
        """세션의 대화 내용을 텍스트로 반환합니다.

        Args:
            session_id: 세션 UUID

        Returns:
            포맷된 대화 텍스트
        """
        transcripts = await self.get_session_transcripts(session_id)
        if not transcripts:
            return ""

        lines = []
        for t in transcripts:
            speaker = t.get("speaker_name") or t.get("speaker_type", "unknown")
            text = t.get("text", "")
            lines.append(f"[{speaker}]: {text}")

        return "\n".join(lines)


class ConsultationAgentResultRepository:
    """에이전트 분석 결과 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

    async def save_result(
        self,
        session_id: UUID,
        result_type: str,
        result_data: Dict[str, Any],
        turn_id: str = None,
        processing_time_ms: int = None,
        model_version: str = None
    ) -> bool:
        """에이전트 분석 결과를 저장합니다.

        Args:
            session_id: 세션 UUID
            result_type: 결과 타입 (intent, sentiment, summary, draft, risk, rag, faq)
            result_data: 결과 데이터
            turn_id: 연관된 turn ID (선택)
            processing_time_ms: 처리 시간 (선택)
            model_version: 모델 버전 (선택)

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            result_json = json.dumps(result_data, ensure_ascii=False, default=str)

            await self.db.execute(
                """
                INSERT INTO consultation_agent_results
                (session_id, turn_id, result_type, result_data, processing_time_ms, model_version)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                """,
                session_id, turn_id, result_type, result_json, processing_time_ms, model_version
            )
            logger.debug(f"Saved {result_type} result for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save agent result: {e}")
            return False

    async def save_intent(
        self,
        session_id: UUID,
        intent: str,
        confidence: float = None,
        turn_id: str = None
    ) -> bool:
        """Intent 결과를 저장합니다."""
        return await self.save_result(
            session_id=session_id,
            result_type="intent",
            result_data={"intent": intent, "confidence": confidence},
            turn_id=turn_id
        )

    async def save_sentiment(
        self,
        session_id: UUID,
        sentiment: str,
        score: float = None,
        turn_id: str = None
    ) -> bool:
        """Sentiment 결과를 저장합니다."""
        return await self.save_result(
            session_id=session_id,
            result_type="sentiment",
            result_data={"sentiment": sentiment, "score": score},
            turn_id=turn_id
        )

    async def save_summary(
        self,
        session_id: UUID,
        summary: str,
        turn_id: str = None
    ) -> bool:
        """Summary 결과를 저장합니다."""
        return await self.save_result(
            session_id=session_id,
            result_type="summary",
            result_data={"summary": summary},
            turn_id=turn_id
        )

    async def save_rag_result(
        self,
        session_id: UUID,
        query: str,
        results: List[Dict[str, Any]],
        turn_id: str = None
    ) -> bool:
        """RAG 검색 결과를 저장합니다."""
        return await self.save_result(
            session_id=session_id,
            result_type="rag",
            result_data={"query": query, "results": results, "count": len(results)},
            turn_id=turn_id
        )

    async def save_faq_result(
        self,
        session_id: UUID,
        query: str,
        faqs: List[Dict[str, Any]],
        cache_hit: bool = False,
        turn_id: str = None
    ) -> bool:
        """FAQ 검색 결과를 저장합니다."""
        return await self.save_result(
            session_id=session_id,
            result_type="faq",
            result_data={"query": query, "faqs": faqs, "count": len(faqs), "cache_hit": cache_hit},
            turn_id=turn_id
        )

    async def get_session_results(
        self,
        session_id: UUID,
        result_type: str = None
    ) -> List[Dict[str, Any]]:
        """세션의 에이전트 결과를 조회합니다.

        Args:
            session_id: 세션 UUID
            result_type: 결과 타입 필터 (선택)

        Returns:
            결과 목록
        """
        if not self.db.is_initialized:
            return []

        try:
            if result_type:
                rows = await self.db.fetch(
                    """
                    SELECT result_id, turn_id, result_type, result_data, processing_time_ms, created_at
                    FROM consultation_agent_results
                    WHERE session_id = $1 AND result_type = $2
                    ORDER BY created_at ASC
                    """,
                    session_id, result_type
                )
            else:
                rows = await self.db.fetch(
                    """
                    SELECT result_id, turn_id, result_type, result_data, processing_time_ms, created_at
                    FROM consultation_agent_results
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    """,
                    session_id
                )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get results for session {session_id}: {e}")
            return []

    async def get_latest_result(
        self,
        session_id: UUID,
        result_type: str
    ) -> Optional[Dict[str, Any]]:
        """세션의 최신 결과를 조회합니다.

        Args:
            session_id: 세션 UUID
            result_type: 결과 타입

        Returns:
            결과 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                """
                SELECT result_id, turn_id, result_type, result_data, processing_time_ms, created_at
                FROM consultation_agent_results
                WHERE session_id = $1 AND result_type = $2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                session_id, result_type
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get latest {result_type} for session {session_id}: {e}")
            return None


# Singleton instances
_session_repo: Optional[ConsultationSessionRepository] = None
_transcript_repo: Optional[ConsultationTranscriptRepository] = None
_agent_result_repo: Optional[ConsultationAgentResultRepository] = None


def get_session_repository() -> ConsultationSessionRepository:
    """ConsultationSessionRepository 싱글톤 인스턴스를 반환합니다."""
    global _session_repo
    if _session_repo is None:
        _session_repo = ConsultationSessionRepository()
    return _session_repo


def get_transcript_repository() -> ConsultationTranscriptRepository:
    """ConsultationTranscriptRepository 싱글톤 인스턴스를 반환합니다."""
    global _transcript_repo
    if _transcript_repo is None:
        _transcript_repo = ConsultationTranscriptRepository()
    return _transcript_repo


def get_agent_result_repository() -> ConsultationAgentResultRepository:
    """ConsultationAgentResultRepository 싱글톤 인스턴스를 반환합니다."""
    global _agent_result_repo
    if _agent_result_repo is None:
        _agent_result_repo = ConsultationAgentResultRepository()
    return _agent_result_repo
