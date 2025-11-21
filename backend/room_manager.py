"""룸 기반 피어 관리 모듈.

이 모듈은 WebRTC 상담 시스템의 룸(방)과 피어(참가자) 관리를 담당합니다.
여러 개의 독립적인 상담 세션(룸)을 동시에 관리하며, 각 룸의 참가자 상태를
추적합니다.

주요 기능:
    - 룸 생성 및 삭제 (자동 생성/비어있을 때 자동 삭제)
    - 참가자 입장/퇴장 관리
    - 룸별 참가자 목록 조회
    - 룸 상태 모니터링 (참가자 수, 참가자 정보)

Architecture:
    - rooms: Dict[str, Dict[str, Peer]] - 룸 이름 → 참가자 맵
    - peer_to_room: Dict[str, str] - 참가자 ID → 룸 이름 (빠른 조회용)

Classes:
    Peer: 참가자 정보를 담는 데이터 클래스
    RoomManager: 룸 및 참가자 관리 클래스

Examples:
    기본 사용법:
        >>> manager = RoomManager()
        >>> manager.join_room("상담실1", "peer-123", "상담사", websocket)
        >>> peers = manager.get_room_peers("상담실1")
        >>> print(f"참가자 수: {len(peers)}")

See Also:
    app.py: WebSocket 시그널링 서버
    peer_manager.py: WebRTC 연결 관리
"""
import logging
import os
from datetime import datetime
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class TranscriptEntry:
    """대화 내용을 나타내는 데이터 클래스.

    Attributes:
        peer_id (str): 발화자의 피어 ID
        nickname (str): 발화자의 닉네임
        text (str): 발화 내용
        timestamp (float): 발화 시간 (Unix timestamp)
    """
    peer_id: str
    nickname: str
    text: str
    timestamp: float


@dataclass
class Peer:
    """룸에 참가한 피어(참가자)를 나타내는 데이터 클래스.

    각 피어는 고유 ID, 닉네임, WebSocket 연결 정보를 포함합니다.
    이 정보는 참가자 간 통신 및 상태 추적에 사용됩니다.

    Attributes:
        peer_id (str): 피어의 고유 식별자 (UUID)
        nickname (str): 사용자가 설정한 표시 이름
        websocket (WebSocket): 피어와의 WebSocket 연결 객체

    Examples:
        >>> peer = Peer(
        ...     peer_id="abc-123-def-456",
        ...     nickname="상담사",
        ...     websocket=websocket_obj
        ... )
        >>> print(f"{peer.nickname} ({peer.peer_id})")
        상담사 (abc-123-def-456)
    """
    peer_id: str
    nickname: str
    websocket: WebSocket


class RoomManager:
    """룸과 피어를 관리하는 핵심 클래스.

    여러 개의 독립적인 룸을 관리하며, 각 룸은 여러 피어를 포함할 수 있습니다.
    상담 시스템에서 여러 상담 세션을 동시에 운영할 수 있게 합니다.

    Attributes:
        rooms (Dict[str, Dict[str, Peer]]): 룸 이름을 키로 하는 룸 딕셔너리
            - 각 룸은 peer_id를 키로 하는 Peer 객체 딕셔너리를 값으로 가짐
        peer_to_room (Dict[str, str]): 피어 ID를 키로 룸 이름을 빠르게 조회하기 위한 역 매핑

    Design Patterns:
        - 이중 맵 구조: 양방향 빠른 조회 지원
        - 자동 생성/삭제: 필요 시 룸 자동 생성, 비어있을 때 자동 삭제

    Thread Safety:
        - 현재 구현은 asyncio 환경에서 단일 스레드로 동작
        - 멀티 스레드 환경에서는 추가 동기화 필요

    Examples:
        >>> manager = RoomManager()
        >>> # 룸 생성 및 참가
        >>> manager.join_room("상담실1", "peer-123", "상담사", ws1)
        >>> manager.join_room("상담실1", "peer-456", "내담자", ws2)
        >>> # 룸 정보 조회
        >>> count = manager.get_room_count("상담실1")
        >>> print(f"참가자: {count}명")
        참가자: 2명
    """

    def __init__(self):
        """RoomManager 초기화.

        빈 룸 딕셔너리와 피어-룸 매핑 딕셔너리를 생성합니다.
        """
        # room_name -> {peer_id: Peer}
        self.rooms: Dict[str, Dict[str, Peer]] = {}

        # peer_id -> room_name (for quick lookup)
        self.peer_to_room: Dict[str, str] = {}

        # room_name -> List[TranscriptEntry] (대화 내용 저장)
        self.room_transcripts: Dict[str, List[TranscriptEntry]] = {}

        # room_name -> start_timestamp (방 시작 시간)
        self.room_start_times: Dict[str, float] = {}

    def create_room(self, room_name: str) -> None:
        """새로운 룸을 생성합니다.

        지정된 이름의 룸이 존재하지 않으면 빈 룸을 생성합니다.
        이미 존재하는 경우 아무 작업도 수행하지 않습니다.

        Args:
            room_name (str): 생성할 룸의 이름

        Note:
            - 일반적으로 직접 호출되지 않고 join_room()에서 자동으로 호출됨
            - 동일한 이름의 룸이 이미 존재하면 무시됨

        Examples:
            >>> manager = RoomManager()
            >>> manager.create_room("상담실1")
            INFO:__main__:Room '상담실1' created
        """
        if room_name not in self.rooms:
            self.rooms[room_name] = {}
            self.room_transcripts[room_name] = []
            self.room_start_times[room_name] = datetime.now().timestamp()
            logger.info(f"Room '{room_name}' created")

    def join_room(self, room_name: str, peer_id: str, nickname: str, websocket: WebSocket) -> None:
        """피어를 지정된 룸에 추가합니다.

        룸이 존재하지 않으면 자동으로 생성한 후 피어를 추가합니다.
        피어 정보는 룸의 참가자 목록과 피어-룸 매핑에 모두 저장됩니다.

        Args:
            room_name (str): 참가할 룸의 이름
            peer_id (str): 참가하는 피어의 고유 ID
            nickname (str): 피어의 표시 이름
            websocket (WebSocket): 피어의 WebSocket 연결 객체

        Note:
            - 룸이 없으면 자동으로 생성됨
            - 동일한 peer_id로 다시 참가하면 기존 정보를 덮어씀
            - 참가 후 룸의 현재 참가자 수가 로그에 기록됨

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws)
            INFO:__main__:Peer '상담사' (peer-123) joined room '상담실1'. Room has 1 peers

            >>> manager.join_room("상담실1", "peer-456", "내담자", ws2)
            INFO:__main__:Peer '내담자' (peer-456) joined room '상담실1'. Room has 2 peers
        """
        # Create room if doesn't exist
        if room_name not in self.rooms:
            self.create_room(room_name)

        # Add peer to room
        peer = Peer(peer_id=peer_id, nickname=nickname, websocket=websocket)
        self.rooms[room_name][peer_id] = peer
        self.peer_to_room[peer_id] = room_name

        logger.info(f"Peer '{nickname}' ({peer_id}) joined room '{room_name}'. "
                   f"Room has {len(self.rooms[room_name])} peers")

    def leave_room(self, peer_id: str) -> Optional[str]:
        """피어를 현재 속한 룸에서 제거합니다.

        피어를 룸의 참가자 목록과 피어-룸 매핑에서 모두 제거합니다.
        룸이 비어있게 되면 자동으로 삭제합니다.

        Args:
            peer_id (str): 퇴장할 피어의 고유 ID

        Returns:
            Optional[str]: 피어가 속해있던 룸 이름.
                          피어가 어떤 룸에도 속하지 않았으면 None

        Note:
            - 마지막 참가자가 퇴장하면 룸이 자동으로 삭제됨
            - 존재하지 않는 피어 ID를 제거하려고 하면 None을 반환

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws)
            >>> room = manager.leave_room("peer-123")
            >>> print(room)
            상담실1
            INFO:__main__:Room '상담실1' deleted (empty)

            >>> # 존재하지 않는 피어
            >>> room = manager.leave_room("non-existent")
            >>> print(room)
            None
        """
        room_name = self.peer_to_room.get(peer_id)
        if not room_name:
            return None

        if room_name in self.rooms and peer_id in self.rooms[room_name]:
            peer = self.rooms[room_name][peer_id]
            nickname = peer.nickname

            # Remove peer
            del self.rooms[room_name][peer_id]
            del self.peer_to_room[peer_id]

            # Delete room if empty
            if not self.rooms[room_name]:
                # Save transcript to file before deleting room
                self._save_transcript_to_file(room_name)

                # Clean up agent for this room
                from agent_manager import remove_agent
                remove_agent(room_name)

                # Clean up room data
                del self.rooms[room_name]
                if room_name in self.room_transcripts:
                    del self.room_transcripts[room_name]
                if room_name in self.room_start_times:
                    del self.room_start_times[room_name]

                logger.info(f"Room '{room_name}' deleted (empty)")
            else:
                logger.info(f"Peer '{nickname}' ({peer_id}) left room '{room_name}'. "
                           f"Room has {len(self.rooms[room_name])} peers")

            return room_name

        return None

    def get_room_peers(self, room_name: str) -> List[Peer]:
        """특정 룸의 모든 피어 목록을 반환합니다.

        Args:
            room_name (str): 조회할 룸의 이름

        Returns:
            List[Peer]: 룸의 모든 피어 리스트.
                       룸이 존재하지 않거나 비어있으면 빈 리스트 반환

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws1)
            >>> manager.join_room("상담실1", "peer-456", "내담자", ws2)
            >>> peers = manager.get_room_peers("상담실1")
            >>> for peer in peers:
            ...     print(f"{peer.nickname} ({peer.peer_id})")
            상담사 (peer-123)
            내담자 (peer-456)
        """
        return list(self.rooms.get(room_name, {}).values())

    def get_other_peers(self, room_name: str, exclude_peer_id: str) -> List[Peer]:
        """특정 피어를 제외한 룸의 다른 모든 피어를 반환합니다.

        브로드캐스트 시 본인을 제외하고 메시지를 전송하거나,
        새 참가자에게 기존 참가자 목록을 알려줄 때 사용됩니다.

        Args:
            room_name (str): 조회할 룸의 이름
            exclude_peer_id (str): 제외할 피어의 ID

        Returns:
            List[Peer]: 제외된 피어를 제외한 모든 피어 리스트.
                       룸이 존재하지 않으면 빈 리스트 반환

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws1)
            >>> manager.join_room("상담실1", "peer-456", "내담자", ws2)
            >>> # peer-123을 제외한 다른 참가자들
            >>> others = manager.get_other_peers("상담실1", "peer-123")
            >>> for peer in others:
            ...     print(peer.nickname)
            내담자
        """
        if room_name not in self.rooms:
            return []
        return [peer for peer in self.rooms[room_name].values()
                if peer.peer_id != exclude_peer_id]

    def get_peer_room(self, peer_id: str) -> Optional[str]:
        """피어가 속한 룸의 이름을 반환합니다.

        Args:
            peer_id (str): 조회할 피어의 ID

        Returns:
            Optional[str]: 피어가 속한 룸 이름.
                          피어가 어떤 룸에도 속하지 않으면 None

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws)
            >>> room = manager.get_peer_room("peer-123")
            >>> print(room)
            상담실1
        """
        return self.peer_to_room.get(peer_id)

    def get_peer(self, peer_id: str) -> Optional[Peer]:
        """피어 ID로 Peer 객체를 조회합니다.

        Args:
            peer_id (str): 조회할 피어의 ID

        Returns:
            Optional[Peer]: Peer 객체. 피어가 존재하지 않으면 None

        Note:
            - peer_to_room 매핑을 통해 빠르게 룸을 찾은 후 피어를 반환
            - 피어가 룸에 없거나 룸이 삭제된 경우 None 반환

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws)
            >>> peer = manager.get_peer("peer-123")
            >>> print(f"{peer.nickname}: {peer.peer_id}")
            상담사: peer-123
        """
        room_name = self.peer_to_room.get(peer_id)
        if room_name and room_name in self.rooms:
            return self.rooms[room_name].get(peer_id)
        return None

    def get_room_list(self) -> List[dict]:
        """모든 룸의 정보를 리스트로 반환합니다.

        각 룸의 이름, 참가자 수, 참가자 상세 정보를 포함합니다.
        관리자 대시보드나 룸 선택 UI에서 사용됩니다.

        Returns:
            List[dict]: 룸 정보 딕셔너리의 리스트
                각 딕셔너리는 다음 키를 포함:
                - room_name (str): 룸 이름
                - peer_count (int): 현재 참가자 수
                - peers (List[dict]): 참가자 정보 리스트
                    - peer_id (str): 참가자 ID
                    - nickname (str): 참가자 닉네임

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws1)
            >>> manager.join_room("상담실2", "peer-456", "관리자", ws2)
            >>> rooms = manager.get_room_list()
            >>> for room in rooms:
            ...     print(f"{room['room_name']}: {room['peer_count']}명")
            상담실1: 1명
            상담실2: 1명
        """
        return [
            {
                "room_name": room_name,
                "peer_count": len(peers),
                "peers": [{"peer_id": p.peer_id, "nickname": p.nickname}
                         for p in peers.values()]
            }
            for room_name, peers in self.rooms.items()
        ]

    def get_room_count(self, room_name: str) -> int:
        """특정 룸의 현재 참가자 수를 반환합니다.

        Args:
            room_name (str): 조회할 룸의 이름

        Returns:
            int: 룸의 현재 참가자 수.
                 룸이 존재하지 않으면 0

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws1)
            >>> manager.join_room("상담실1", "peer-456", "내담자", ws2)
            >>> count = manager.get_room_count("상담실1")
            >>> print(f"참가자: {count}명")
            참가자: 2명

            >>> # 존재하지 않는 룸
            >>> count = manager.get_room_count("없는룸")
            >>> print(count)
            0
        """
        return len(self.rooms.get(room_name, {}))

    def add_transcript(self, peer_id: str, room_name: str, text: str, timestamp: Optional[float] = None):
        """대화 내용을 룸의 transcript 히스토리에 추가합니다.

        Args:
            peer_id (str): 발화자의 피어 ID
            room_name (str): 룸 이름
            text (str): 발화 내용
            timestamp (float, optional): 발화 시간. None이면 현재 시간 사용

        Examples:
            >>> manager = RoomManager()
            >>> manager.join_room("상담실1", "peer-123", "상담사", ws)
            >>> manager.add_transcript("peer-123", "상담실1", "안녕하세요")
        """
        if room_name not in self.room_transcripts:
            self.room_transcripts[room_name] = []

        # Get peer nickname
        peer = self.get_peer(peer_id)
        nickname = peer.nickname if peer else "Unknown"

        # Use current time if not provided
        if timestamp is None:
            timestamp = datetime.now().timestamp()

        entry = TranscriptEntry(
            peer_id=peer_id,
            nickname=nickname,
            text=text,
            timestamp=timestamp
        )
        self.room_transcripts[room_name].append(entry)
        logger.debug(f"Added transcript to room '{room_name}': {nickname}: {text}")

    def _save_transcript_to_file(self, room_name: str):
        """룸의 대화 내용을 텍스트 파일로 저장합니다.

        Args:
            room_name (str): 저장할 룸의 이름

        Note:
            - 파일은 data/transcripts/ 디렉토리에 저장됨
            - 파일명: room_{room_name}_{timestamp}.txt
            - 포맷: [시:분:초] 이름: 메시지
        """
        transcripts = self.room_transcripts.get(room_name, [])
        if not transcripts:
            logger.info(f"No transcripts to save for room '{room_name}'")
            return

        # Create data/transcripts directory if not exists
        os.makedirs("data/transcripts", exist_ok=True)

        # Generate filename with timestamp
        end_time = datetime.now()
        filename = f"room_{room_name}_{end_time.strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join("data", "transcripts", filename)

        # Get room start time
        start_timestamp = self.room_start_times.get(room_name, transcripts[0].timestamp)
        start_time = datetime.fromtimestamp(start_timestamp)

        # Write to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Write header
                f.write(f"[상담실: {room_name}]\n")
                f.write(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"총 메시지 수: {len(transcripts)}\n")
                f.write("=" * 60 + "\n\n")

                # Write each transcript
                for entry in transcripts:
                    msg_time = datetime.fromtimestamp(entry.timestamp)
                    time_str = msg_time.strftime('%H:%M:%S')
                    f.write(f"{entry.nickname} [{time_str}]: {entry.text}\n")

            logger.info(f"💾 Saved transcript for room '{room_name}' to {filepath} ({len(transcripts)} messages)")
        except Exception as e:
            logger.error(f"Failed to save transcript for room '{room_name}': {e}")
