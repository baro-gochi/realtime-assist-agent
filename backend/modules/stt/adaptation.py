"""Google Cloud Speech-to-Text v2 Adaptation 설정 모듈.

이 모듈은 음성 인식의 정확도를 높이기 위한 PhraseSet과 CustomClass 기능을 제공합니다.

## 핵심 개념

### PhraseSet (구문 집합)
특정 단어나 구문의 인식 확률을 높이는 "힌트"를 제공합니다.

**사용 사례:**
- 도메인 특화 용어 (예: 의료 용어, 법률 용어)
- 자주 사용되는 명령어 (예: "결제 취소", "배송 조회")
- 혼동되기 쉬운 단어 구분 (예: "배송" vs "배송료")

**Boost 값:**
- 범위: 0 초과 ~ 20 이하
- 높을수록 해당 구문 인식 확률 증가
- 너무 높으면 거짓 양성(false positive) 증가
- 권장: 5-15 사이에서 시작, 이진 탐색으로 최적값 찾기

### CustomClass (커스텀 클래스)
관련된 항목들의 그룹을 정의하여 PhraseSet에서 참조합니다.

**사용 사례:**
- 상품명 목록 (수백 개의 상품명 중 하나)
- 회사명/브랜드명 목록
- 지역명/도시명 목록
- 서비스명 목록

**PhraseSet과의 관계:**
CustomClass는 단독으로 사용되지 않고, PhraseSet의 phrase에서 참조됩니다.
- 인라인 CustomClass: SpeechAdaptation.custom_classes에 정의
- PhraseSet에서 "${custom_class_name}" 형태로 참조

## 사용 예시

```python
from modules.stt import STTAdaptationConfig

# 1. 기본 사용 (YAML 파일에서 로드)
config = STTAdaptationConfig.from_yaml("stt_phrases.yaml")
adaptation = config.build_adaptation()

# 2. 코드에서 직접 정의
config = STTAdaptationConfig()
config.add_phrase("결제 취소", boost=10)
config.add_phrase("배송 조회", boost=10)
config.add_custom_class("products", ["아이폰", "갤럭시", "픽셀"])
config.add_phrase("${products} 주문", boost=15)

# 3. stt_service.py와 통합
# RecognitionConfig.adaptation 필드에 적용
```

## 참고 문서
- https://cloud.google.com/speech-to-text/docs/adaptation-model
- https://cloud.google.com/speech-to-text/v2/docs

Examples:
    >>> from modules.stt import STTAdaptationConfig
    >>> config = STTAdaptationConfig()
    >>> config.add_phrase("고객 상담", boost=10)
    >>> adaptation = config.build_adaptation()
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    from google.cloud.speech_v2.types import cloud_speech
    GOOGLE_SPEECH_AVAILABLE = True
except ImportError:
    GOOGLE_SPEECH_AVAILABLE = False
    cloud_speech = None  # type: ignore

# 타입 힌트용 (런타임에는 영향 없음)
if TYPE_CHECKING:
    from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types
    SpeechAdaptationType = cloud_speech_types.SpeechAdaptation
else:
    SpeechAdaptationType = Any

logger = logging.getLogger(__name__)


@dataclass
class Phrase:
    """단일 구문 정의.

    Attributes:
        value: 인식할 구문 텍스트
        boost: 가중치 (0 초과 ~ 20 이하, None이면 PhraseSet 기본값 사용)

    Examples:
        >>> phrase = Phrase("결제 취소", boost=10)
        >>> phrase = Phrase("${products} 주문", boost=15)  # CustomClass 참조
    """
    value: str
    boost: Optional[float] = None

    def __post_init__(self):
        if self.boost is not None and (self.boost <= 0 or self.boost > 20):
            raise ValueError(f"Boost must be between 0 (exclusive) and 20 (inclusive), got {self.boost}")


@dataclass
class PhraseSetConfig:
    """PhraseSet 구성.

    Attributes:
        name: PhraseSet 이름 (인라인 사용 시 선택적)
        phrases: 구문 목록
        boost: 기본 가중치 (개별 phrase.boost가 없을 때 적용)
        display_name: 표시 이름 (최대 63자)

    Examples:
        >>> phrase_set = PhraseSetConfig(
        ...     name="customer_service",
        ...     phrases=[Phrase("결제 취소", 10), Phrase("배송 조회", 10)],
        ...     boost=5
        ... )
    """
    name: str = ""
    phrases: List[Phrase] = field(default_factory=list)
    boost: Optional[float] = None
    display_name: str = ""

    def add_phrase(self, value: str, boost: Optional[float] = None):
        """구문 추가."""
        self.phrases.append(Phrase(value=value, boost=boost))


@dataclass
class CustomClassConfig:
    """CustomClass 구성.

    Attributes:
        name: 클래스 이름 (PhraseSet에서 ${name}으로 참조)
        items: 클래스에 속하는 항목 목록
        display_name: 표시 이름 (최대 63자)

    Examples:
        >>> custom_class = CustomClassConfig(
        ...     name="products",
        ...     items=["아이폰", "갤럭시", "픽셀"],
        ...     display_name="상품 목록"
        ... )
    """
    name: str
    items: List[str] = field(default_factory=list)
    display_name: str = ""

    def add_item(self, value: str):
        """항목 추가."""
        self.items.append(value)


class STTAdaptationConfig:
    """Speech-to-Text Adaptation 설정 관리자.

    PhraseSet과 CustomClass를 관리하고 Google Cloud Speech v2 API 형식으로 변환합니다.

    Attributes:
        phrase_sets: PhraseSet 구성 목록
        custom_classes: CustomClass 구성 목록
        enabled: adaptation 기능 활성화 여부

    Examples:
        기본 사용:
            >>> config = STTAdaptationConfig()
            >>> config.add_phrase("결제 취소", boost=10)
            >>> adaptation = config.build_adaptation()

        YAML에서 로드:
            >>> config = STTAdaptationConfig.from_yaml("phrases.yaml")

        stt_service.py와 통합:
            >>> from modules.stt import get_default_adaptation
            >>> adaptation = get_default_adaptation()
            >>> # RecognitionConfig(adaptation=adaptation)
    """

    def __init__(self, enabled: bool = True):
        """초기화.

        Args:
            enabled: adaptation 기능 활성화 여부 (False면 build_adaptation()이 None 반환)
        """
        self.phrase_sets: List[PhraseSetConfig] = []
        self.custom_classes: List[CustomClassConfig] = []
        self.enabled = enabled
        self._default_phrase_set = PhraseSetConfig(name="default")

    def add_phrase(self, value: str, boost: Optional[float] = None) -> "STTAdaptationConfig":
        """기본 PhraseSet에 구문 추가.

        Args:
            value: 인식할 구문 (예: "결제 취소", "${products} 주문")
            boost: 가중치 (0 초과 ~ 20 이하)

        Returns:
            self (메서드 체이닝 지원)

        Examples:
            >>> config.add_phrase("결제 취소", boost=10)
            >>> config.add_phrase("배송 조회", boost=10)
        """
        self._default_phrase_set.add_phrase(value, boost)
        return self

    def add_phrases(self, phrases: List[str], boost: Optional[float] = None) -> "STTAdaptationConfig":
        """기본 PhraseSet에 여러 구문 추가.

        Args:
            phrases: 구문 목록
            boost: 모든 구문에 적용할 가중치

        Returns:
            self (메서드 체이닝 지원)
        """
        for phrase in phrases:
            self.add_phrase(phrase, boost)
        return self

    def add_phrase_set(self, phrase_set: PhraseSetConfig) -> "STTAdaptationConfig":
        """PhraseSet 추가.

        Args:
            phrase_set: PhraseSet 구성

        Returns:
            self (메서드 체이닝 지원)
        """
        self.phrase_sets.append(phrase_set)
        return self

    def add_custom_class(
        self,
        name: str,
        items: List[str],
        display_name: str = ""
    ) -> "STTAdaptationConfig":
        """CustomClass 추가.

        Args:
            name: 클래스 이름 (PhraseSet에서 ${name}으로 참조)
            items: 클래스 항목 목록
            display_name: 표시 이름

        Returns:
            self (메서드 체이닝 지원)

        Examples:
            >>> config.add_custom_class("products", ["아이폰", "갤럭시", "픽셀"])
            >>> config.add_phrase("${products} 주문", boost=15)
        """
        self.custom_classes.append(CustomClassConfig(
            name=name,
            items=items,
            display_name=display_name
        ))
        return self

    def build_adaptation(self) -> Optional[SpeechAdaptationType]:
        """Google Cloud Speech v2 SpeechAdaptation 객체 생성.

        Returns:
            SpeechAdaptation 객체 또는 None (비활성화 또는 설정 없음)

        Raises:
            ImportError: google-cloud-speech 패키지 미설치 시

        Note:
            - enabled=False면 None 반환
            - phrase_sets와 custom_classes 모두 비어있으면 None 반환
        """
        if not self.enabled:
            logger.debug("STT adaptation is disabled")
            return None

        if not GOOGLE_SPEECH_AVAILABLE:
            logger.warning("google-cloud-speech package not installed, adaptation disabled")
            return None

        # 기본 phrase_set 처리
        all_phrase_sets = list(self.phrase_sets)
        if self._default_phrase_set.phrases:
            all_phrase_sets.insert(0, self._default_phrase_set)

        # 설정이 없으면 None 반환
        if not all_phrase_sets and not self.custom_classes:
            logger.debug("No phrases or custom classes configured")
            return None

        # AdaptationPhraseSet 목록 생성
        adaptation_phrase_sets = []
        for ps_config in all_phrase_sets:
            # value는 str, boost는 float로 변환 (YAML에서 숫자가 int로 파싱될 수 있음)
            phrases = []
            for p in ps_config.phrases:
                if p.boost is not None:
                    phrases.append(cloud_speech.PhraseSet.Phrase(value=str(p.value), boost=float(p.boost)))
                else:
                    phrases.append(cloud_speech.PhraseSet.Phrase(value=str(p.value)))

            # PhraseSet의 boost도 동일하게 처리
            if ps_config.boost is not None:
                inline_phrase_set = cloud_speech.PhraseSet(phrases=phrases, boost=float(ps_config.boost))
            else:
                inline_phrase_set = cloud_speech.PhraseSet(phrases=phrases)

            adaptation_phrase_sets.append(
                cloud_speech.SpeechAdaptation.AdaptationPhraseSet(
                    inline_phrase_set=inline_phrase_set
                )
            )

        # CustomClass는 Google Cloud에 먼저 리소스로 생성해야 사용 가능
        # v2 API에서는 inline CustomClass를 지원하지 않음
        # 향후 필요시 CreateCustomClass API로 미리 생성 후 참조
        # 현재는 PhraseSet만 사용
        if self.custom_classes:
            logger.warning(
                f"CustomClass {len(self.custom_classes)}개는 v2 API에서 inline 지원 안됨, 무시됨. "
                "Google Cloud Console에서 먼저 생성 필요."
            )

        adaptation = cloud_speech.SpeechAdaptation(
            phrase_sets=adaptation_phrase_sets,
        )

        phrase_count = sum(len(ps.phrases) for ps in all_phrase_sets)
        logger.info(f"STT adaptation configured: {phrase_count} phrases")

        return adaptation

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "STTAdaptationConfig":
        """딕셔너리에서 설정 로드.

        Args:
            data: 설정 딕셔너리

        Returns:
            STTAdaptationConfig 인스턴스

        Expected format:
            {
                "enabled": true,
                "phrases": [
                    {"value": "결제 취소", "boost": 10},
                    "배송 조회"  # boost 없이 문자열만도 가능
                ],
                "phrase_sets": [
                    {
                        "name": "commands",
                        "boost": 5,
                        "phrases": [...]
                    }
                ],
                "custom_classes": [
                    {
                        "name": "products",
                        "items": ["아이폰", "갤럭시"]
                    }
                ]
            }
        """
        config = cls(enabled=data.get("enabled", True))

        # 단순 phrases 처리
        for phrase in data.get("phrases", []):
            if isinstance(phrase, str):
                config.add_phrase(phrase)
            elif isinstance(phrase, dict):
                config.add_phrase(phrase["value"], phrase.get("boost"))

        # phrase_sets 처리
        for ps_data in data.get("phrase_sets", []):
            ps_config = PhraseSetConfig(
                name=ps_data.get("name", ""),
                boost=ps_data.get("boost"),
                display_name=ps_data.get("display_name", "")
            )
            for phrase in ps_data.get("phrases", []):
                if isinstance(phrase, str):
                    ps_config.add_phrase(phrase)
                elif isinstance(phrase, dict):
                    ps_config.add_phrase(phrase["value"], phrase.get("boost"))
            config.add_phrase_set(ps_config)

        # custom_classes 처리
        for cc_data in data.get("custom_classes", []):
            config.add_custom_class(
                name=cc_data["name"],
                items=cc_data.get("items", []),
                display_name=cc_data.get("display_name", "")
            )

        return config

    @classmethod
    def from_yaml(cls, path: str) -> "STTAdaptationConfig":
        """YAML 파일에서 설정 로드.

        Args:
            path: YAML 파일 경로

        Returns:
            STTAdaptationConfig 인스턴스

        Raises:
            ImportError: PyYAML 미설치 시
            FileNotFoundError: 파일이 없을 때
        """
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml")

        file_path = Path(path)
        if not file_path.exists():
            logger.warning(f"Adaptation config file not found: {path}")
            return cls(enabled=False)

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        logger.info(f"Loaded STT adaptation config from: {path}")
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, path: str) -> "STTAdaptationConfig":
        """JSON 파일에서 설정 로드.

        Args:
            path: JSON 파일 경로

        Returns:
            STTAdaptationConfig 인스턴스
        """
        import json

        file_path = Path(path)
        if not file_path.exists():
            logger.warning(f"Adaptation config file not found: {path}")
            return cls(enabled=False)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info(f"Loaded STT adaptation config from: {path}")
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """설정을 딕셔너리로 변환."""
        return {
            "enabled": self.enabled,
            "phrases": [
                {"value": p.value, "boost": p.boost} if p.boost else p.value
                for p in self._default_phrase_set.phrases
            ],
            "phrase_sets": [
                {
                    "name": ps.name,
                    "boost": ps.boost,
                    "display_name": ps.display_name,
                    "phrases": [
                        {"value": p.value, "boost": p.boost} if p.boost else p.value
                        for p in ps.phrases
                    ]
                }
                for ps in self.phrase_sets
            ],
            "custom_classes": [
                {
                    "name": cc.name,
                    "display_name": cc.display_name,
                    "items": cc.items
                }
                for cc in self.custom_classes
            ]
        }


# === 기본 설정 로더 ===

_default_config: Optional[STTAdaptationConfig] = None


def get_default_adaptation() -> Optional[SpeechAdaptationType]:
    """기본 adaptation 설정을 로드하여 반환.

    다음 순서로 설정 파일을 찾습니다:
    1. 환경 변수 STT_ADAPTATION_CONFIG 경로
    2. backend/config/stt_phrases.yaml
    3. backend/config/stt_phrases.json

    Returns:
        SpeechAdaptation 객체 또는 None

    Examples:
        >>> from modules.stt import get_default_adaptation
        >>> adaptation = get_default_adaptation()
        >>> # RecognitionConfig에서 사용
        >>> recognition_config = cloud_speech.RecognitionConfig(
        ...     adaptation=adaptation,
        ...     ...
        ... )
    """
    global _default_config

    if _default_config is not None:
        return _default_config.build_adaptation()

    # Config에서 경로 가져오기 (순환 참조 방지를 위해 lazy import)
    from .config import adaptation_config

    config_path = adaptation_config.config_path

    if config_path and config_path.exists():
        if config_path.suffix in (".yaml", ".yml"):
            _default_config = STTAdaptationConfig.from_yaml(str(config_path))
        else:
            _default_config = STTAdaptationConfig.from_json(str(config_path))
        return _default_config.build_adaptation()

    # 설정 파일 없음 - 빈 설정
    logger.debug("No STT adaptation config file found, using empty config")
    _default_config = STTAdaptationConfig(enabled=False)
    return None


def reload_adaptation_config() -> Optional[SpeechAdaptationType]:
    """adaptation 설정을 다시 로드.

    설정 파일이 변경되었을 때 호출하여 새 설정을 적용합니다.

    Returns:
        SpeechAdaptation 객체 또는 None
    """
    global _default_config
    _default_config = None
    return get_default_adaptation()


# === 고객 상담 도메인 기본 구문 ===

def create_customer_service_adaptation(
    additional_phrases: Optional[List[str]] = None,
    product_names: Optional[List[str]] = None,
) -> STTAdaptationConfig:
    """고객 상담 도메인용 기본 adaptation 설정 생성.

    Args:
        additional_phrases: 추가 구문 목록
        product_names: 상품명 목록 (CustomClass로 등록)

    Returns:
        STTAdaptationConfig 인스턴스

    Examples:
        >>> config = create_customer_service_adaptation(
        ...     product_names=["아이폰", "갤럭시", "픽셀"]
        ... )
        >>> adaptation = config.build_adaptation()
    """
    config = STTAdaptationConfig()

    # 기본 상담 구문 (한국어)
    default_phrases = [
        # 인사/마무리
        ("안녕하세요", 5),
        ("감사합니다", 5),
        ("죄송합니다", 5),

        # 주문/결제
        ("주문 취소", 10),
        ("결제 취소", 10),
        ("환불 요청", 10),
        ("카드 결제", 8),
        ("무통장 입금", 8),

        # 배송
        ("배송 조회", 10),
        ("배송 지연", 10),
        ("배송비", 8),
        ("반품 접수", 10),
        ("교환 신청", 10),

        # 문의
        ("고객 상담", 8),
        ("상담원 연결", 10),
        ("문의 사항", 8),
        ("AS 접수", 10),
    ]

    for phrase, boost in default_phrases:
        config.add_phrase(phrase, boost)

    # 추가 구문
    if additional_phrases:
        for phrase in additional_phrases:
            config.add_phrase(phrase, boost=8)

    # 상품명 CustomClass
    if product_names:
        config.add_custom_class("products", product_names, "상품 목록")
        config.add_phrase("${products}", boost=15)
        config.add_phrase("${products} 주문", boost=12)
        config.add_phrase("${products} 문의", boost=12)

    return config
