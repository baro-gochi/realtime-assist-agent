"""데이터베이스 레포지토리 모듈.

각 테이블에 대한 CRUD 작업을 제공합니다.

Classes:
    RoomRepository: 룸/참가자 관련 데이터 저장
    TranscriptRepository: 대화 내용 저장
    SystemLogRepository: 시스템 로그 저장
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from .connection import get_db_manager

logger = logging.getLogger(__name__)


class RoomRepository:
    """룸 및 참가자 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

    async def create_room(self, room_name: str, metadata: dict = None) -> Optional[UUID]:
        """새로운 룸을 생성합니다.

        Args:
            room_name: 룸 이름
            metadata: 추가 메타데이터 (선택)

        Returns:
            생성된 룸의 UUID 또는 None
        """
        if not self.db.is_initialized:
            logger.warning("Database not initialized, skipping room creation")
            return None

        try:
            import json
            metadata_json = json.dumps(metadata or {})

            room_id = await self.db.fetchval(
                """
                INSERT INTO rooms (room_name, metadata)
                VALUES ($1, $2::jsonb)
                RETURNING id
                """,
                room_name, metadata_json
            )
            logger.info(f"Created room '{room_name}' with id: {room_id}")
            return room_id
        except Exception as e:
            logger.error(f"Failed to create room '{room_name}': {e}")
            return None

    async def end_room(self, room_id: UUID) -> bool:
        """룸을 종료 상태로 변경합니다.

        Args:
            room_id: 룸 UUID

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                UPDATE rooms
                SET ended_at = NOW(), status = 'ended'
                WHERE id = $1
                """,
                room_id
            )
            logger.info(f"Room {room_id} marked as ended")
            return True
        except Exception as e:
            logger.error(f"Failed to end room {room_id}: {e}")
            return False

    async def add_peer(
        self,
        room_id: UUID,
        peer_id: str,
        nickname: str
    ) -> bool:
        """참가자를 룸에 추가합니다.

        Args:
            room_id: 룸 UUID
            peer_id: 피어 ID (WebSocket UUID)
            nickname: 닉네임

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                INSERT INTO peers (room_id, peer_id, nickname)
                VALUES ($1, $2, $3)
                ON CONFLICT (room_id, peer_id) DO UPDATE
                SET nickname = EXCLUDED.nickname, joined_at = NOW(), left_at = NULL
                """,
                room_id, peer_id, nickname
            )
            logger.debug(f"Added peer '{nickname}' ({peer_id}) to room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add peer {peer_id}: {e}")
            return False

    async def remove_peer(self, room_id: UUID, peer_id: str) -> bool:
        """참가자의 퇴장 시간을 기록합니다.

        Args:
            room_id: 룸 UUID
            peer_id: 피어 ID

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                UPDATE peers
                SET left_at = NOW()
                WHERE room_id = $1 AND peer_id = $2
                """,
                room_id, peer_id
            )
            logger.debug(f"Peer {peer_id} left room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove peer {peer_id}: {e}")
            return False

    async def get_room_by_name(self, room_name: str, active_only: bool = True) -> Optional[Dict]:
        """룸 이름으로 룸 정보를 조회합니다.

        Args:
            room_name: 룸 이름
            active_only: 활성 룸만 조회할지 여부

        Returns:
            룸 정보 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            query = "SELECT * FROM rooms WHERE room_name = $1"
            if active_only:
                query += " AND status = 'active'"
            query += " ORDER BY created_at DESC LIMIT 1"

            row = await self.db.fetchrow(query, room_name)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get room '{room_name}': {e}")
            return None

    async def get_room_summary(self, room_id: UUID) -> Optional[Dict]:
        """룸 요약 정보를 조회합니다.

        Args:
            room_id: 룸 UUID

        Returns:
            룸 요약 딕셔너리 또는 None
        """
        if not self.db.is_initialized:
            return None

        try:
            row = await self.db.fetchrow(
                "SELECT * FROM room_conversation_summary WHERE room_id = $1",
                room_id
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get room summary {room_id}: {e}")
            return None


class TranscriptRepository:
    """대화 내용 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

    async def add_transcript(
        self,
        room_id: UUID,
        peer_id: str,
        nickname: str,
        text: str,
        timestamp: float,
        source: str = "google",
        is_final: bool = True
    ) -> bool:
        """대화 내용을 저장합니다.

        Args:
            room_id: 룸 UUID
            peer_id: 발화자 피어 ID
            nickname: 발화자 닉네임
            text: 발화 내용
            timestamp: 발화 시간 (Unix timestamp)
            source: STT 소스 (기본값: google)
            is_final: 최종 결과 여부

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            ts = datetime.fromtimestamp(timestamp)
            await self.db.execute(
                """
                INSERT INTO transcripts (room_id, peer_id, nickname, text, timestamp, source, is_final)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                room_id, peer_id, nickname, text, ts, source, is_final
            )
            logger.debug(f"Saved transcript: {nickname}: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
            return False

    async def get_room_transcripts(
        self,
        room_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """룸의 대화 내용을 조회합니다.

        Args:
            room_id: 룸 UUID
            limit: 조회 개수 제한
            offset: 시작 위치

        Returns:
            대화 내용 리스트
        """
        if not self.db.is_initialized:
            return []

        try:
            rows = await self.db.fetch(
                """
                SELECT peer_id, nickname, text, timestamp, source, is_final
                FROM transcripts
                WHERE room_id = $1
                ORDER BY timestamp ASC
                LIMIT $2 OFFSET $3
                """,
                room_id, limit, offset
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get transcripts for room {room_id}: {e}")
            return []

    async def save_agent_summary(
        self,
        room_id: UUID,
        summary_text: str,
        last_summarized_index: int = 0
    ) -> bool:
        """에이전트 요약을 저장합니다.

        Args:
            room_id: 룸 UUID
            summary_text: 요약 텍스트
            last_summarized_index: 마지막 요약 인덱스

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            await self.db.execute(
                """
                INSERT INTO agent_summaries (room_id, summary_text, last_summarized_index)
                VALUES ($1, $2, $3)
                """,
                room_id, summary_text, last_summarized_index
            )
            logger.debug(f"Saved agent summary for room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save agent summary: {e}")
            return False


class SystemLogRepository:
    """시스템 로그 데이터 저장소."""

    def __init__(self):
        self.db = get_db_manager()

    async def add_log(
        self,
        level: str,
        message: str,
        logger_name: str = None,
        module: str = None,
        func_name: str = None,
        line_no: int = None,
        exception: str = None,
        extra: dict = None
    ) -> bool:
        """시스템 로그를 저장합니다.

        Args:
            level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: 로그 메시지
            logger_name: 로거 이름
            module: 모듈 이름
            func_name: 함수 이름
            line_no: 라인 번호
            exception: 예외 정보
            extra: 추가 데이터

        Returns:
            성공 여부
        """
        if not self.db.is_initialized:
            return False

        try:
            import json
            extra_json = json.dumps(extra or {})

            await self.db.execute(
                """
                INSERT INTO system_logs
                (level, message, logger_name, module, func_name, line_no, exception, extra)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """,
                level, message, logger_name, module, func_name, line_no, exception, extra_json
            )
            return True
        except Exception as e:
            # 로그 저장 실패는 콘솔에만 출력 (무한 루프 방지)
            print(f"Failed to save system log: {e}")
            return False

    async def get_logs(
        self,
        level: str = None,
        logger_name: str = None,
        since: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """시스템 로그를 조회합니다.

        Args:
            level: 로그 레벨 필터
            logger_name: 로거 이름 필터
            since: 시작 시간
            limit: 조회 개수 제한

        Returns:
            로그 리스트
        """
        if not self.db.is_initialized:
            return []

        try:
            conditions = []
            params = []
            param_idx = 1

            if level:
                conditions.append(f"level = ${param_idx}")
                params.append(level)
                param_idx += 1

            if logger_name:
                conditions.append(f"logger_name = ${param_idx}")
                params.append(logger_name)
                param_idx += 1

            if since:
                conditions.append(f"created_at >= ${param_idx}")
                params.append(since)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)

            query = f"""
                SELECT * FROM system_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx}
            """

            rows = await self.db.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get system logs: {e}")
            return []

    async def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """오래된 로그를 정리합니다.

        Args:
            days_to_keep: 보관 일수

        Returns:
            삭제된 로그 수
        """
        if not self.db.is_initialized:
            return 0

        try:
            result = await self.db.fetchval(
                "SELECT cleanup_old_logs($1)",
                days_to_keep
            )
            logger.info(f"Cleaned up {result} old log entries")
            return result or 0
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0
