"""STT 모듈 설정.

Google Cloud Speech-to-Text v2 API 관련 설정값.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# 환경변수 로드 (상위에서 이미 로드됨)
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_env_path = Path(__file__).parent.parent.parent / "config" / ".env"
load_dotenv(_env_path)


def _parse_bool(value: str, default: bool = True) -> bool:
    """문자열을 bool로 변환."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


# ============================================================
# Google Cloud 인증 설정
# ============================================================

@dataclass(frozen=True)
class GoogleCloudConfig:
    """Google Cloud 인증 설정."""

    # 서비스 계정 키 파일 경로
    CREDENTIALS_PATH: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # 프로젝트 ID (v2 API 필수)
    PROJECT_ID: Optional[str] = os.getenv("GOOGLE_CLOUD_PROJECT")

    @property
    def is_configured(self) -> bool:
        """인증 설정 완료 여부."""
        return bool(self.CREDENTIALS_PATH and self.PROJECT_ID)


# ============================================================
# STT 인식 설정
# ============================================================

@dataclass
class RecognitionConfig:
    """음성 인식 설정."""

    # 언어 코드
    LANGUAGE_CODE: str = field(
        default_factory=lambda: os.getenv("STT_LANGUAGE_CODE", "ko-KR")
    )

    # 인식 모델 (short, long, telephony 등)
    MODEL: str = field(
        default_factory=lambda: os.getenv("STT_MODEL", "short")
    )

    # 리전 (global, us, eu 등)
    LOCATION: str = field(
        default_factory=lambda: os.getenv("STT_LOCATION", "global")
    )

    # 샘플레이트 (Hz)
    SAMPLE_RATE_HERTZ: int = field(
        default_factory=lambda: int(os.getenv("STT_SAMPLE_RATE_HERTZ", "48000"))
    )

    # 자동 구두점
    ENABLE_AUTOMATIC_PUNCTUATION: bool = field(
        default_factory=lambda: _parse_bool(
            os.getenv("STT_ENABLE_AUTOMATIC_PUNCTUATION"), default=True
        )
    )

    # Adaptation (PhraseSet/CustomClass) 활성화
    ENABLE_ADAPTATION: bool = field(
        default_factory=lambda: _parse_bool(
            os.getenv("STT_ENABLE_ADAPTATION"), default=True
        )
    )

    @property
    def language_codes(self) -> List[str]:
        """언어 코드 리스트 반환."""
        return [self.LANGUAGE_CODE]


# ============================================================
# Adaptation 설정 경로
# ============================================================

# backend 디렉토리 경로 (모든 상대 경로의 기준)
BACKEND_DIR: Path = Path(__file__).parent.parent.parent


@dataclass(frozen=True)
class AdaptationConfig:
    """Adaptation 설정 파일 경로."""

    # 커스텀 설정 파일 경로 (환경변수로 지정)
    CUSTOM_CONFIG_PATH: Optional[str] = os.getenv("STT_ADAPTATION_CONFIG")

    # 기본 설정 파일 경로 (backend/config/)
    DEFAULT_YAML_PATH: Path = BACKEND_DIR / "config" / "stt_phrases.yaml"
    DEFAULT_JSON_PATH: Path = BACKEND_DIR / "config" / "stt_phrases.json"

    @property
    def config_path(self) -> Optional[Path]:
        """사용할 설정 파일 경로 반환.

        상대 경로는 backend 디렉토리 기준으로 해석됩니다.
        절대 경로는 그대로 사용됩니다.
        """
        if self.CUSTOM_CONFIG_PATH:
            custom_path = Path(self.CUSTOM_CONFIG_PATH)
            # 상대 경로면 backend 기준으로 변환
            if not custom_path.is_absolute():
                custom_path = BACKEND_DIR / custom_path
            return custom_path
        if self.DEFAULT_YAML_PATH.exists():
            return self.DEFAULT_YAML_PATH
        if self.DEFAULT_JSON_PATH.exists():
            return self.DEFAULT_JSON_PATH
        return None


# ============================================================
# 스트리밍 설정
# ============================================================

@dataclass(frozen=True)
class StreamingConfig:
    """스트리밍 인식 설정."""

    # 타겟 샘플레이트 (Hz) - WebRTC 48kHz 직접 전송
    TARGET_SAMPLE_RATE: int = 48000

    # 청크 지속 시간 (초) - 250ms
    CHUNK_DURATION: float = 0.25

    # 스트림 청크 크기 제한 (bytes)
    MAX_CHUNK_SIZE: int = 25600  # 25KB

    # 스트림 타임아웃 (초)
    STREAM_TIMEOUT: int = 300  # 5분

    # 오디오 버퍼 크기
    AUDIO_BUFFER_SIZE: int = 4096

    # 무음 감지 임계값 (초)
    SILENCE_THRESHOLD: float = 1.0


# ============================================================
# 싱글톤 인스턴스
# ============================================================

google_cloud_config = GoogleCloudConfig()
recognition_config = RecognitionConfig()
adaptation_config = AdaptationConfig()
streaming_config = StreamingConfig()


# ============================================================
# 설정 로드 확인 로그
# ============================================================

logger.info(f"[STT] 설정 로드: .env={_env_path} (존재: {_env_path.exists()})")
logger.info(f"[STT] Google Cloud 설정: {google_cloud_config.is_configured}")
logger.info(f"[STT] 프로젝트 ID: {google_cloud_config.PROJECT_ID}")
logger.info(f"[STT] 언어: {recognition_config.LANGUAGE_CODE}, 모델: {recognition_config.MODEL}")
logger.info(f"[STT] 샘플레이트: {streaming_config.TARGET_SAMPLE_RATE}Hz")
logger.info(f"[STT] 어댑테이션 활성화: {recognition_config.ENABLE_ADAPTATION}")
if recognition_config.ENABLE_ADAPTATION:
    _adaptation_path = adaptation_config.config_path
    logger.info(f"[STT] 어댑테이션 설정 파일: {_adaptation_path} (존재: {_adaptation_path.exists() if _adaptation_path else 'N/A'})")
