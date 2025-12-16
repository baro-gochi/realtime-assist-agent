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
        logger.info(f"[세션생성] 시작 - agent_name={agent_name}, room_id={room_id}, agent_id={agent_id}, channel={channel}")

        if not self.db.is_initialized:
            logger.warning("[세션생성] 실패: 데이터베이스 초기화 안됨")
            return None

        logger.debug(f"[세션생성] DB 초기화 확인 완료")

        try:
            metadata_json = json.dumps(metadata or {})
            logger.debug(f"[세션생성] 메타데이터 JSON 변환 완료: {metadata_json}")

            logger.info(f"[세션생성] INSERT 실행 중 - room_id={room_id} (type={type(room_id).__name__})")
            session_id = await self.db.fetchval(
                """
                INSERT INTO consultation_sessions
                (room_id, customer_id, agent_id, agent_name, channel, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING session_id
                """,
                room_id, customer_id, agent_id, agent_name, channel, metadata_json
            )

            if session_id:
                logger.info(f"[세션생성] 성공 - session_id={session_id}")
            else:
                logger.warning(f"[세션생성] 실패: session_id가 None으로 반환됨")

            return session_id
        except Exception as e:
            logger.error(f"[세션생성] 예외 발생: {type(e).__name__}: {e}", exc_info=True)
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
        logger.info(f"[고객연결] 시작 - session_id={session_id}, customer_id={customer_id}")
        if not self.db.is_initialized:
            logger.warning(f"[고객연결] 스킵: DB 미초기화")
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
            logger.info(f"[고객연결] 성공 - session_id={session_id}, customer_id={customer_id}")
            return True
        except Exception as e:
            logger.error(f"[고객연결] 실패 - session_id={session_id}: {e}", exc_info=True)
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
        logger.info(f"[세션종료] 시작 - session_id={session_id}, type={consultation_type}")
        logger.debug(f"end_session params: consultation_type='{consultation_type}' (type: {type(consultation_type).__name__})")

        if not self.db.is_initialized:
            logger.warning("[세션종료] 실패: 데이터베이스 초기화 안됨")
            return False

        try:
            # 현재 세션 상태 확인
            current_status = await self.db.fetchval(
                "SELECT status FROM consultation_sessions WHERE session_id = $1",
                session_id
            )
            logger.debug(f"current session status: {current_status}")

            logger.info(f"[세션종료] DB 함수 호출 중 - end_consultation_session({session_id}, summary길이={len(final_summary) if final_summary else 0}, type='{consultation_type}')")
            result = await self.db.fetchval(
                "SELECT end_consultation_session($1, $2, $3)",
                session_id, final_summary, consultation_type
            )
            logger.debug(f"DB function result: {result}")

            if result:
                # 저장 후 확인
                saved_type = await self.db.fetchval(
                    "SELECT consultation_type FROM consultation_sessions WHERE session_id = $1",
                    session_id
                )
                logger.debug(f"saved consultation_type in DB: '{saved_type}'")
                logger.info(f"[세션종료] 성공 - session_id={session_id}")
            else:
                logger.warning(f"[세션종료] 결과 없음 - session_id={session_id} (status가 active가 아닐 수 있음)")
            return bool(result)
        except Exception as e:
            logger.error(f"[세션종료] 예외 발생: {type(e).__name__}: {e}", exc_info=True)
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
        logger.debug(f"[전사저장] 시작 - session_id={session_id}, turn={turn_index}, speaker={speaker_name}")

        if not self.db.is_initialized:
            logger.warning("[전사저장] 실패: 데이터베이스 초기화 안됨")
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
            logger.info(f"[전사저장] 성공 - session={session_id}, turn={turn_index}, text={text[:30]}...")
            return True
        except Exception as e:
            logger.error(f"[전사저장] 예외 발생: {type(e).__name__}: {e}", exc_info=True)
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
        logger.debug(f"[결과저장] 시작 - session_id={session_id}, type={result_type}, turn_id={turn_id}")

        if not self.db.is_initialized:
            logger.warning("[결과저장] 실패: 데이터베이스 초기화 안됨")
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
            logger.info(f"[결과저장] 성공 - session={session_id}, type={result_type}")
            return True
        except Exception as e:
            logger.error(f"[결과저장] 예외 발생: {type(e).__name__}: {e}", exc_info=True)
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


# ============================================================================
# 상담사(Agent) 저장소
# ============================================================================


class AgentRepository:
    """상담사 데이터 저장소.

    상담사 등록, 조회, 상담 이력 조회 기능을 제공합니다.
    agent_code는 사용자가 입력하는 사번/ID이고, agent_id는 DB의 auto-increment ID입니다.
    """

    def __init__(self):
        self.db = get_db_manager()

    async def register_agent(
        self,
        agent_code: str,
        agent_name: str
    ) -> Optional[int]:
        """새로운 상담사를 등록합니다.

        Args:
            agent_code: 상담사 코드 (사번 등 사용자 입력 ID)
            agent_name: 상담사 이름

        Returns:
            생성된 상담사의 DB ID 또는 None
        """
        if not self.db.is_initialized:
            logger.warning("Database not initialized, skipping agent registration")
            return None

        try:
            # 중복 체크
            existing = await self.db.fetchrow(
                """
                SELECT agent_id FROM agents
                WHERE agent_code = $1
                """,
                agent_code
            )
            if existing:
                logger.warning(f"Agent with code {agent_code} already exists")
                return None

            agent_id = await self.db.fetchval(
                """
                INSERT INTO agents (agent_code, agent_name)
                VALUES ($1, $2)
                RETURNING agent_id
                """,
                agent_code, agent_name
            )
            logger.info(f"Registered agent: {agent_name} (code: {agent_code}, id: {agent_id})")
            return agent_id
        except Exception as e:
            logger.error(f"Failed to register agent: {e}")
            return None

    async def find_agent(
        self,
        agent_code: str,
        agent_name: str
    ) -> Optional[Dict[str, Any]]:
        """상담사 코드와 이름으로 상담사를 조회합니다.

        Args:
            agent_code: 상담사 코드 (사번)
            agent_name: 상담사 이름

        Returns:
            상담사 정보 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                """
                SELECT agent_id, agent_code, agent_name, created_at
                FROM agents
                WHERE agent_code = $1 AND agent_name = $2
                """,
                agent_code, agent_name
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to find agent: {e}")
            return None

    async def get_agent_by_id(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """DB ID로 상담사를 조회합니다."""
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                """
                SELECT agent_id, agent_code, agent_name, created_at
                FROM agents
                WHERE agent_id = $1
                """,
                agent_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get agent by id: {e}")
            return None

    async def get_all_agents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """전체 상담사 목록을 조회합니다.

        Args:
            limit: 조회 개수 제한 (기본값: 100)

        Returns:
            상담사 정보 리스트
        """
        if not self.db.is_initialized:
            logger.warning("Database not initialized, skipping agent list query")
            return []

        try:
            rows = await self.db.fetch(
                """
                SELECT agent_id, agent_code, agent_name, created_at
                FROM agents
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit
            )
            result = []
            for row in rows:
                item = dict(row)
                if item.get('created_at'):
                    item['created_at'] = str(item['created_at'])
                result.append(item)
            logger.info(f"Found {len(result)} agents")
            return result
        except Exception as e:
            logger.error(f"Failed to get all agents: {e}")
            return []

    async def get_agent_sessions(
        self,
        agent_id: int,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """상담사의 상담 세션 목록을 조회합니다.

        Args:
            agent_id: 상담사 DB ID
            limit: 조회 개수 제한

        Returns:
            세션 목록
        """
        if not self.db.is_initialized:
            return []

        try:
            # consultation_sessions 테이블의 agent_id는 문자열로 저장됨
            rows = await self.db.fetch(
                """
                SELECT
                    cs.session_id,
                    cs.room_id,
                    cs.customer_id,
                    cs.agent_name,
                    cs.channel,
                    cs.started_at,
                    cs.ended_at,
                    cs.final_summary,
                    cs.metadata,
                    c.customer_name,
                    c.phone_number,
                    (SELECT COUNT(*) FROM consultation_transcripts ct WHERE ct.session_id = cs.session_id) as transcript_count,
                    EXTRACT(EPOCH FROM (COALESCE(cs.ended_at, NOW()) - cs.started_at))::int as duration_seconds
                FROM consultation_sessions cs
                LEFT JOIN customers c ON cs.customer_id = c.customer_id
                WHERE cs.agent_id = $1::text
                ORDER BY cs.started_at DESC
                LIMIT $2
                """,
                str(agent_id), limit
            )
            result = []
            for row in rows:
                item = dict(row)
                # datetime/UUID 변환
                for key in ['started_at', 'ended_at']:
                    if item.get(key):
                        item[key] = str(item[key])
                if item.get('session_id'):
                    item['session_id'] = str(item['session_id'])
                if item.get('room_id'):
                    item['room_id'] = str(item['room_id'])
                result.append(item)
            return result
        except Exception as e:
            logger.error(f"Failed to get agent sessions: {e}")
            return []


_agent_repo: Optional[AgentRepository] = None


def get_agent_repository() -> AgentRepository:
    """AgentRepository 싱글톤 인스턴스를 반환합니다."""
    global _agent_repo
    if _agent_repo is None:
        _agent_repo = AgentRepository()
    return _agent_repo
