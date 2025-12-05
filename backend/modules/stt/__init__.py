"""STT (Speech-to-Text) 모듈.

Google Cloud Speech-to-Text v2 API를 사용한 음성 인식 기능을 제공합니다.

Classes:
    STTService: 실시간 오디오 스트리밍 STT 서비스
    STTAdaptationConfig: PhraseSet/CustomClass 설정 관리자

Config:
    google_cloud_config: Google Cloud 인증 설정
    recognition_config: 음성 인식 설정
    adaptation_config: Adaptation 파일 경로 설정
    streaming_config: 스트리밍 설정
"""

from .service import STTService
from .adaptation import (
    STTAdaptationConfig,
    get_default_adaptation,
    reload_adaptation_config,
    create_customer_service_adaptation,
    Phrase,
    PhraseSetConfig,
    CustomClassConfig,
)
from .config import (
    google_cloud_config,
    recognition_config,
    adaptation_config,
    streaming_config,
    GoogleCloudConfig,
    RecognitionConfig,
    AdaptationConfig,
    StreamingConfig,
)

__all__ = [
    # Service
    "STTService",
    # Adaptation
    "STTAdaptationConfig",
    "get_default_adaptation",
    "reload_adaptation_config",
    "create_customer_service_adaptation",
    "Phrase",
    "PhraseSetConfig",
    "CustomClassConfig",
    # Config
    "google_cloud_config",
    "recognition_config",
    "adaptation_config",
    "streaming_config",
    "GoogleCloudConfig",
    "RecognitionConfig",
    "AdaptationConfig",
    "StreamingConfig",
]
