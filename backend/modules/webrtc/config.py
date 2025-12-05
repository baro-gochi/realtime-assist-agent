"""WebRTC 모듈 설정.

TURN/STUN 서버, ICE 설정 등 WebRTC 관련 상수와 환경변수 기반 설정.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# 환경변수 로드 (상위에서 이미 로드됨)
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_env_path = Path(__file__).parent.parent.parent / "config" / ".env"
load_dotenv(_env_path)


# ============================================================
# ICE Server 설정
# ============================================================

@dataclass(frozen=True)
class ICEServerConfig:
    """ICE 서버 설정."""

    # TURN 서버
    TURN_SERVER_URL: Optional[str] = os.getenv("TURN_SERVER_URL")
    TURN_USERNAME: Optional[str] = os.getenv("TURN_USERNAME")
    TURN_CREDENTIAL: Optional[str] = os.getenv("TURN_CREDENTIAL")

    # STUN 서버
    STUN_SERVER_URL: Optional[str] = os.getenv("STUN_SERVER_URL")

    # 기본 공개 STUN 서버 (fallback)
    DEFAULT_STUN_SERVERS: tuple = (
        "stun:stun.l.google.com:19302",
        "stun:stun1.l.google.com:19302",
    )

    @property
    def has_turn_server(self) -> bool:
        """TURN 서버 설정 완료 여부."""
        return all([self.TURN_SERVER_URL, self.TURN_USERNAME, self.TURN_CREDENTIAL])


# ============================================================
# 데이터 저장 경로
# ============================================================

@dataclass(frozen=True)
class StorageConfig:
    """데이터 저장 경로 설정."""

    # 기본 데이터 디렉토리
    DATA_DIR: Path = Path("data")

    # 트랜스크립트 저장 경로
    TRANSCRIPTS_DIR: Path = DATA_DIR / "transcripts"

    def ensure_dirs(self) -> None:
        """필요한 디렉토리 생성."""
        self.TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# WebRTC 연결 설정
# ============================================================

@dataclass(frozen=True)
class ConnectionConfig:
    """WebRTC 연결 관련 설정."""

    # ICE 연결 타임아웃 (초)
    ICE_CONNECTION_TIMEOUT: int = 30

    # 피어 연결 유휴 타임아웃 (초)
    PEER_IDLE_TIMEOUT: int = 300

    # 오디오 프레임 크기 (samples)
    AUDIO_FRAME_SIZE: int = 960  # 20ms @ 48kHz

    # 오디오 샘플레이트 (Hz)
    AUDIO_SAMPLE_RATE: int = 48000

    # STT 엔진 타입
    STT_ENGINE: str = "google"

    # 최대 대기 시간 (초)
    MAX_WAIT_TIME: float = 5.0


# ============================================================
# 싱글톤 인스턴스
# ============================================================

ice_config = ICEServerConfig()
storage_config = StorageConfig()
connection_config = ConnectionConfig()


# ============================================================
# 설정 로드 확인 로그
# ============================================================

logger.info(f"[WebRTC Config] .env 경로: {_env_path} (존재: {_env_path.exists()})")
logger.info(f"[WebRTC Config] TURN 서버 설정 완료: {ice_config.has_turn_server}")
if ice_config.TURN_SERVER_URL:
    logger.info(f"[WebRTC Config] TURN URL: {ice_config.TURN_SERVER_URL}")
if ice_config.STUN_SERVER_URL:
    logger.info(f"[WebRTC Config] STUN URL: {ice_config.STUN_SERVER_URL}")
else:
    logger.info(f"[WebRTC Config] STUN URL: 기본 Google STUN 사용")
logger.info(f"[WebRTC Config] STT 엔진: {connection_config.STT_ENGINE}")
logger.info(f"[WebRTC Config] 오디오 샘플레이트: {connection_config.AUDIO_SAMPLE_RATE}Hz")
