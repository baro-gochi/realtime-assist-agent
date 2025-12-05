"""Backend modules package.

이 패키지는 WebRTC 기반 실시간 상담 시스템의 핵심 모듈을 포함합니다.

Modules:
    webrtc: WebRTC 피어 연결 및 룸 관리
    stt: Google Cloud Speech-to-Text 음성 인식
    agent: LangGraph 기반 대화 요약 에이전트
"""

from .webrtc import PeerConnectionManager, RoomManager, AudioRelayTrack
from .stt import STTService, STTAdaptationConfig
from .agent import create_agent_graph, get_or_create_agent, remove_agent, RoomAgent

__all__ = [
    # WebRTC
    "PeerConnectionManager",
    "RoomManager",
    "AudioRelayTrack",
    # STT
    "STTService",
    "STTAdaptationConfig",
    # Agent
    "create_agent_graph",
    "get_or_create_agent",
    "remove_agent",
    "RoomAgent",
]
