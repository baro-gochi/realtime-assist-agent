"""WebRTC 모듈.

피어 연결 관리, 룸 관리, 오디오 트랙 릴레이 기능을 제공합니다.

Classes:
    PeerConnectionManager: WebRTC 피어 연결 및 SFU 릴레이 관리
    RoomManager: 룸 및 참가자 관리
    AudioRelayTrack: STT 처리용 오디오 프레임 캡처 트랙
    Peer: 참가자 데이터 클래스
    TranscriptEntry: 대화 내용 데이터 클래스

Config:
    ice_config: ICE 서버 설정
    storage_config: 데이터 저장 경로 설정
    connection_config: WebRTC 연결 설정
"""

from .tracks import AudioRelayTrack
from .room_manager import RoomManager, Peer, TranscriptEntry
from .peer_manager import PeerConnectionManager
from .config import (
    ice_config,
    storage_config,
    connection_config,
    ICEServerConfig,
    StorageConfig,
    ConnectionConfig,
)

__all__ = [
    # Classes
    "AudioRelayTrack",
    "RoomManager",
    "Peer",
    "TranscriptEntry",
    "PeerConnectionManager",
    # Config
    "ice_config",
    "storage_config",
    "connection_config",
    "ICEServerConfig",
    "StorageConfig",
    "ConnectionConfig",
]
