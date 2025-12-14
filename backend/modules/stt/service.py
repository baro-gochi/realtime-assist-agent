"""Google Cloud Speech-to-Text v2 서비스 통합 모듈.

이 모듈은 Google Cloud Speech-to-Text API v2를 사용하여 실시간 오디오 스트림을
텍스트로 변환하는 기능을 제공합니다.

주요 기능:
    - 실시간 오디오 스트림 인식 (Streaming Recognition)
    - WebRTC 오디오 프레임을 Google STT API 형식으로 변환
    - 비동기 처리를 통한 높은 처리량
    - 한국어 음성 인식 최적화

Architecture:
    - Google Cloud Speech-to-Text API v2 사용
    - Recognizer 기반 스트리밍 인식
    - AudioFrame → PCM bytes 변환 파이프라인
    - 자동 구두점 및 실시간 결과 지원

Examples:
    기본 사용법:
        >>> from modules.stt import STTService
        >>> service = STTService()
        >>> async for text in service.process_audio_stream(audio_frames):
        ...     print(f"인식된 텍스트: {text}")

    커스텀 설정:
        >>> service = STTService(
        ...     language_codes=["ko-KR"],
        ...     model="chirp",
        ...     enable_automatic_punctuation=True
        ... )

See Also:
    webrtc.peer_manager: 오디오 프레임 캡처
    app.py: WebSocket을 통한 결과 전송
    Google Cloud Speech-to-Text V2 Documentation:
        https://cloud.google.com/speech-to-text/v2/docs
"""
import asyncio
import logging
from typing import AsyncIterator, Optional, List
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.api_core.client_options import ClientOptions
from google.protobuf.duration_pb2 import Duration
from av import AudioFrame
import numpy as np
import queue
import threading

# Config 모듈
from .config import (
    google_cloud_config,
    recognition_config,
    streaming_config as stt_streaming_config,
)

# Adaptation 모듈 (동일 패키지에서 import)
try:
    from .adaptation import get_default_adaptation, STTAdaptationConfig
    ADAPTATION_AVAILABLE = True
except ImportError:
    ADAPTATION_AVAILABLE = False
    get_default_adaptation = None
    STTAdaptationConfig = None

logger = logging.getLogger(__name__)


class STTService:
    """Google Cloud Speech-to-Text v2 서비스 래퍼 클래스.

    WebRTC 오디오 스트림을 실시간으로 텍스트로 변환합니다.
    v2 API의 Recognizer 기반 스트리밍 인식을 사용합니다.

    Attributes:
        client (SpeechClient): Google Cloud Speech v2 동기 API 클라이언트
        project_id (str): Google Cloud 프로젝트 ID
        recognizer (str): Recognizer 리소스 경로
        language_codes (List[str]): 음성 인식 언어 코드 리스트
        model (str): 사용할 음성 인식 모델
        enable_automatic_punctuation (bool): 자동 구두점 추가 여부
        enable_adaptation (bool): 음성 적응(PhraseSet/CustomClass) 활성화 여부
        adaptation (SpeechAdaptation): 음성 적응 설정 객체

    Note:
        - GOOGLE_APPLICATION_CREDENTIALS 환경 변수 필수
        - GOOGLE_CLOUD_PROJECT 환경 변수 필수 (프로젝트 ID)
        - WebRTC 오디오는 자동으로 인코딩 감지됨
        - 25KB 스트림 제한 주의
        - adaptation 설정: backend/config/stt_phrases.yaml 파일 또는 STT_ADAPTATION_CONFIG 환경 변수

    Examples:
        >>> from modules.stt import STTService
        >>> service = STTService()
        >>> # 오디오 스트림 처리
        >>> async for transcript in service.process_audio_stream(audio_queue):
        ...     print(f"인식 결과: {transcript}")

    See Also:
        adaptation.py: PhraseSet/CustomClass 설정 모듈
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        language_codes: Optional[List[str]] = None,
        model: Optional[str] = None,
        enable_automatic_punctuation: Optional[bool] = None,
        enable_adaptation: Optional[bool] = None,
    ):
        """STTService 초기화.

        Args:
            project_id (str, optional): Google Cloud 프로젝트 ID.
                환경 변수 GOOGLE_CLOUD_PROJECT 또는 필수
            language_codes (List[str], optional): 음성 인식 언어 코드 리스트.
                환경 변수 STT_LANGUAGE_CODE 또는 ["ko-KR"] 사용
            model (str, optional): 음성 인식 모델.
                환경 변수 STT_MODEL 또는 "chirp" 사용
            enable_automatic_punctuation (bool, optional): 자동 구두점 추가.
                환경 변수 STT_ENABLE_AUTOMATIC_PUNCTUATION 또는 True 사용
            enable_adaptation (bool, optional): 음성 적응(PhraseSet/CustomClass) 활성화.
                환경 변수 STT_ENABLE_ADAPTATION 또는 True 사용.
                stt_phrases.yaml 파일이 있으면 자동 로드.

        Raises:
            ValueError: GOOGLE_CLOUD_PROJECT 미설정 시

        Note:
            - .env 파일에서 환경 변수 로드 필요
            - 서비스 계정 키 파일 권한 확인 필요
            - v2 API는 Recognizer 개념 필수
            - adaptation 설정은 backend/config/stt_phrases.yaml 파일 참조
        """
        # Google Cloud 인증 및 프로젝트 확인 프로젝트 ID (v2에서 필수)
        if not google_cloud_config.CREDENTIALS_PATH:
            logger.warning(
                "GOOGLE_APPLICATION_CREDENTIALS not set. "
                "STT service may not work properly."
            )

        self.project_id = project_id or google_cloud_config.PROJECT_ID
        if not self.project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable must be set for v2 API"
            )

        # Configuration from config or parameters
        self.language_codes = language_codes or recognition_config.language_codes

        self.model = model or recognition_config.MODEL
        self.sample_rate = stt_streaming_config.TARGET_SAMPLE_RATE
        self.input_sample_rate = recognition_config.SAMPLE_RATE_HERTZ

        # Location 설정 (리전별 엔드포인트 지원)
        self.location = recognition_config.LOCATION

        # Regional endpoint 설정
        if self.location != "global":
            api_endpoint = f"{self.location}-speech.googleapis.com"
            client_options = ClientOptions(api_endpoint=api_endpoint)
            self.client = SpeechClient(client_options=client_options)
            logger.info(f"[STT] 리전 엔드포인트 사용: {api_endpoint}")
        else:
            self.client = SpeechClient()
            logger.info("[STT] 글로벌 엔드포인트 사용: speech.googleapis.com")

        # Recognizer path
        self.recognizer = f"projects/{self.project_id}/locations/{self.location}/recognizers/_"

        self.enable_automatic_punctuation = (
            enable_automatic_punctuation
            if enable_automatic_punctuation is not None
            else recognition_config.ENABLE_AUTOMATIC_PUNCTUATION
        )

        # Adaptation (PhraseSet/CustomClass) 설정
        self.enable_adaptation = (
            enable_adaptation
            if enable_adaptation is not None
            else recognition_config.ENABLE_ADAPTATION
        )
        self.adaptation = None
        if self.enable_adaptation and ADAPTATION_AVAILABLE:
            try:
                self.adaptation = get_default_adaptation()
                if self.adaptation:
                    logger.info("[STT] 어댑테이션 설정 로드 완료")
            except Exception as e:
                logger.warning(f"[STT] 어댑테이션 로드 실패: {e}")

        logger.info(
            f"[STT] 서비스 v2 초기화 완료: "
            f"프로젝트={self.project_id}, "
            f"위치={self.location}, "
            f"언어={self.language_codes}, "
            f"모델={self.model}, "
            f"샘플레이트={self.sample_rate}Hz, "
            f"구두점={'활성' if self.enable_automatic_punctuation else '비활성'}, "
            f"어댑테이션={'활성' if self.adaptation else '비활성'}"
        )

    def _create_streaming_config(self) -> cloud_speech.StreamingRecognitionConfig:
        """스트리밍 인식을 위한 Google STT v2 설정 생성.

        Returns:
            cloud_speech.StreamingRecognitionConfig: 스트리밍 인식 설정 객체

        Note:
            - ExplicitDecodingConfig: WebRTC 오디오 형식 명시적 지정
            - language_codes: 다중 언어 지원 (리스트)
            - model: latest_long 등
        """
        recognition_cfg = cloud_speech.RecognitionConfig(
            explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.sample_rate,
                audio_channel_count=1,
            ),
            language_codes=self.language_codes,
            model=self.model,
        )

        # Features 설정 (구두점 등)
        if self.enable_automatic_punctuation:
            recognition_cfg.features = cloud_speech.RecognitionFeatures(
                enable_automatic_punctuation=True
            )

        # Adaptation 설정 (PhraseSet/CustomClass)
        if self.adaptation:
            recognition_cfg.adaptation = self.adaptation

        # StreamingRecognitionConfig 생성
        streaming_config_message = cloud_speech.StreamingRecognitionConfig(
            config=recognition_cfg,
        )

        # StreamingRecognitionFeatures 설정
        # enable_voice_activity_events=False: Google VAD 비활성화
        #   - True: Google이 음성 종료 감지 시 즉시 스트림 종료 (잦은 재시작)
        #   - False: 스트림 유지, is_final로 문장 단위 결과는 정상 수신 (5분 제한)
        streaming_config_message.streaming_features = cloud_speech.StreamingRecognitionFeatures(
            enable_voice_activity_events=False,
        )

        return streaming_config_message

    async def _audio_frame_to_bytes(self, frame: AudioFrame) -> bytes:
        """AudioFrame을 Google STT API 형식의 PCM bytes로 변환.

        WebRTC AudioFrame을 16-bit PCM 바이트 배열로 변환합니다.

        Args:
            frame (AudioFrame): WebRTC 오디오 프레임

        Returns:
            bytes: 16-bit PCM 오디오 데이터

        Note:
            - AudioFrame.to_ndarray()로 numpy 배열 추출
            - int16 형식으로 변환 (Google STT 요구사항)
            - 스테레오는 모노로 변환 (채널 평균)
            - 낮은 볼륨 자동 증폭
        """
        # Convert AudioFrame to numpy array
        array = frame.to_ndarray()

        # Handle stereo to mono conversion properly
        # First flatten if multi-dimensional
        if array.ndim > 1:
            array = array.flatten()

        # Check if size suggests stereo (2x samples for interleaved L-R-L-R)
        if array.size == frame.samples * 2:
            # Interleaved stereo: reshape to (samples, 2) and average channels
            array = array.reshape(-1, 2).mean(axis=1).astype(array.dtype)

        # Handle WebRTC audio format conversion
        if array.dtype in (np.float32, np.float64):
            # Float format - convert to int16
            array = (array * 32767).astype(np.int16)
        elif array.dtype == np.int16:
            # Apply gain to low volume audio
            max_val = np.abs(array).max()
            if max_val > 0 and max_val < 8000:
                # Target: 30% of full range (~10000) for reliable STT recognition
                target_level = 10000.0
                gain = min(target_level / max_val, 150.0)  # Cap gain at 150x for very quiet audio
                array = np.clip(array * gain, -32768, 32767).astype(np.int16)

        return array.tobytes()

    async def process_audio_stream(
        self,
        audio_queue: asyncio.Queue
    ) -> AsyncIterator[dict]:
        """오디오 프레임 큐를 처리하여 텍스트로 변환.

        비동기 제너레이터로 연속적인 음성 인식 결과를 스트리밍합니다.

        Args:
            audio_queue (asyncio.Queue): AudioFrame 객체를 담은 비동기 큐

        Yields:
            dict: 인식 결과
                - transcript (str): 인식된 텍스트
                - is_final (bool): 최종 결과 여부
                - confidence (float): 신뢰도 점수

        Note:
            - 큐에서 None을 받으면 스트림 종료
            - 인식 실패 시 에러 로그 기록 후 계속 진행
            - 25KB 청크 제한 준수
            - v2 API는 recognizer 파라미터 필수
            - 동기 클라이언트를 스레드에서 실행하여 비동기 호환

        Examples:
            >>> audio_queue = asyncio.Queue()
            >>> service = STTService()
            >>> async for text in service.process_audio_stream(audio_queue):
            ...     await websocket.send_json({
            ...         "type": "transcript",
            ...         "data": {"text": text}
            ...     })
        """
        streaming_config_message = self._create_streaming_config()

        # Thread-safe queue to bridge asyncio and sync code
        sync_queue = queue.Queue()
        stop_event = threading.Event()

        # Background task to transfer frames from asyncio queue to sync queue
        async def transfer_frames():
            """asyncio Queue에서 thread-safe Queue로 프레임 전송"""
            chunk_count = 0
            try:
                logger.info("[STT] 프레임 전송 태스크 시작...")
                while not stop_event.is_set():
                    frame = await audio_queue.get()
                    if frame is None:
                        logger.info("[STT] 오디오 스트림 종료 (None 수신)")
                        sync_queue.put(None)
                        break

                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info(f"[STT] 첫 번째 오디오 프레임 수신, 전송 시작...")

                    sync_queue.put(frame)
                logger.info(f"[STT] 프레임 전송 완료. 총 청크: {chunk_count}")
            except Exception as e:
                logger.error(f"[STT] 프레임 전송 오류: {e}", exc_info=True)
                sync_queue.put(None)

        # Start frame transfer task
        transfer_task = asyncio.create_task(transfer_frames())

        def generate_requests():
            """동기 요청 생성기 (v2 방식) - 250ms 청크 누적 전송"""
            try:
                # First request with recognizer and config
                logger.info("[STT] 초기 설정 요청 전송 중...")
                config_request = cloud_speech.StreamingRecognizeRequest(
                    recognizer=self.recognizer,
                    streaming_config=streaming_config_message,
                )
                yield config_request
                logger.info("[STT] 설정 요청 완료, 오디오 프레임 대기 중...")

                # 250ms 청크 누적 방식
                frame_count = 0
                chunk_count = 0
                accumulated_arrays = []
                accumulated_duration = 0.0
                last_frame_time = None
                # WebRTC 프레임 자체가 안 오는 경우의 타임아웃 (연결 끊김 감지)
                # voice_activity_timeout과 일치 (Google 최대 60초)
                silence_threshold = 60.0
                first_frame_timeout = 60.0

                def process_accumulated_chunks():
                    """누적된 오디오를 처리하여 전송 (48kHz 직접 전송, 리샘플링 없음)"""
                    nonlocal chunk_count
                    if not accumulated_arrays:
                        return None

                    # 모든 배열을 하나로 합침
                    combined_array = np.concatenate(accumulated_arrays)
                    combined_array = combined_array.astype(np.int16)

                    chunk_count += 1

                    # 오디오 상태 로그 (첫 청크 + 100청크마다)
                    if chunk_count == 1 or chunk_count % 100 == 0:
                        max_val = np.abs(combined_array).max()
                        mean_val = np.abs(combined_array).mean()
                        non_zero = np.count_nonzero(combined_array)
                        logger.info(
                            f"[STT] 오디오 청크 #{chunk_count}: 샘플수={len(combined_array)}, "
                            f"최대={max_val}, 평균={mean_val:.1f}, 비제로={non_zero}/{len(combined_array)}"
                        )

                    audio_bytes = combined_array.tobytes()
                    return audio_bytes

                while True:
                    try:
                        # Wait longer for first frame, shorter for subsequent frames
                        timeout = first_frame_timeout if frame_count == 0 else 0.1
                        frame = sync_queue.get(timeout=timeout)
                    except queue.Empty:
                        # 타임아웃 시 누적된 오디오가 있으면 전송
                        if accumulated_arrays:
                            audio_bytes = process_accumulated_chunks()
                            if audio_bytes:
                                yield cloud_speech.StreamingRecognizeRequest(audio=audio_bytes)
                            accumulated_arrays = []
                            accumulated_duration = 0.0

                        # Check if we should close stream due to prolonged silence
                        if last_frame_time is not None:
                            import time
                            silence_duration = time.time() - last_frame_time
                            if silence_duration > silence_threshold:
                                logger.info(f"[STT] {silence_duration:.1f}초간 오디오 없음, 스트림 정상 종료...")
                                break
                        elif frame_count == 0:
                            # No frames received at all after long wait
                            logger.error(f"[STT] {first_frame_timeout}초 타임아웃 후에도 오디오 프레임 수신 없음!")
                            break
                        continue

                    if frame is None:
                        # 스트림 종료 전 남은 오디오 전송
                        if accumulated_arrays:
                            audio_bytes = process_accumulated_chunks()
                            if audio_bytes:
                                yield cloud_speech.StreamingRecognizeRequest(audio=audio_bytes)
                        logger.info(f"[STT] 스트림 종료 신호 수신. 총 프레임: {frame_count}, 전송 청크: {chunk_count}")
                        break

                    # Update last frame time
                    import time
                    last_frame_time = time.time()

                    frame_count += 1
                    if frame_count == 1:
                        logger.info(f"[STT] 오디오 프레임 정보 - 샘플레이트: {frame.sample_rate}, 포맷: {frame.format.name}, 샘플수: {frame.samples}")

                    # Convert frame to numpy array
                    array = frame.to_ndarray()

                    # Handle stereo to mono conversion
                    if array.ndim > 1:
                        array = array.flatten()

                    if array.size == frame.samples * 2:
                        array = array.reshape(-1, 2).mean(axis=1).astype(array.dtype)
                        if frame_count == 1:
                            logger.info(f"[STT] 스테레오를 모노로 변환")

                    # Handle audio format conversion
                    if array.dtype == np.float32 or array.dtype == np.float64:
                        array = (array * 32767).astype(np.int16)
                    elif array.dtype == np.int16:
                        # Apply gain to low volume audio
                        max_val = np.abs(array).max()
                        if max_val > 0 and max_val < 5000:
                            gain = min(6500.0 / max_val, 20.0)
                            array = np.clip(array * gain, -32768, 32767).astype(np.int16)

                    # 프레임 누적
                    accumulated_arrays.append(array)
                    frame_duration = frame.samples / frame.sample_rate
                    accumulated_duration += frame_duration

                    # 250ms 이상 누적되면 전송 (config에서 가져온 값 사용)
                    if accumulated_duration >= stt_streaming_config.CHUNK_DURATION:
                        audio_bytes = process_accumulated_chunks()
                        if audio_bytes:
                            chunk_size = len(audio_bytes)
                            if chunk_size > 25000:
                                logger.warning(f"[STT] 오디오 청크 크기 {chunk_size}가 25KB 제한 초과, 분할 중...")
                                for i in range(0, len(audio_bytes), self.input_sample_rate):
                                    chunk = audio_bytes[i:i+self.input_sample_rate]
                                    yield cloud_speech.StreamingRecognizeRequest(audio=chunk)
                            else:
                                yield cloud_speech.StreamingRecognizeRequest(audio=audio_bytes)

                            if chunk_count % 200 == 0:  # ~50초마다 로그
                                logger.info(f"[STT] Google STT로 {chunk_count}개 청크 전송 완료")

                        # 누적 초기화
                        accumulated_arrays = []
                        accumulated_duration = 0.0
            except Exception as e:
                logger.error(f"[STT] 요청 생성 오류: {e}", exc_info=True)
                return

        # Result queue to get transcripts from thread
        result_queue = queue.Queue()

        def run_streaming_recognize():
            """동기 STT 호출을 스레드에서 실행"""
            try:
                logger.info(f"[STT] 스트리밍 인식 시작 (recognizer: {self.recognizer})")
                logger.info(f"[STT] API 엔드포인트: {self.client._transport._host if hasattr(self.client, '_transport') else 'unknown'}")

                logger.info("[STT] streaming_recognize() 호출 중...")
                responses_iterator = self.client.streaming_recognize(
                    requests=generate_requests()
                )
                logger.info("[STT] streaming_recognize() 반환됨, 반복 시작...")

                logger.info("[STT] STT API 첫 응답 대기 중...")

                response_count = 0
                for response in responses_iterator:
                    if response_count == 0:
                        logger.info("[STT] 스트림 연결 완료, 첫 응답 수신!")
                    else:
                        logger.info(f"[STT] 대기 후 응답 수신...")
                    response_count += 1
                    logger.info(f"[STT] 응답 #{response_count} 수신")

                    if not response.results:
                        logger.info(f"[STT] 응답 #{response_count} 결과 없음 (빈 응답)")
                        continue

                    result = response.results[0]
                    logger.info(f"[STT] 응답 #{response_count}: is_final={result.is_final}, 후보수={len(result.alternatives) if result.alternatives else 0}")

                    if result.is_final:
                        if result.alternatives:
                            transcript = result.alternatives[0].transcript
                            confidence = result.alternatives[0].confidence

                            logger.info(
                                f"[STT] 인식 결과 (최종): '{transcript}' "
                                f"(신뢰도: {confidence:.2f})"
                            )

                            result_queue.put({
                                "transcript": transcript,
                                "is_final": True,
                                "confidence": confidence
                            })

                    logger.info(f"[STT] 응답 #{response_count + 1} 대기 중...")

                # Signal end of stream
                logger.info(f"[STT] 응답 반복자 종료. 총 응답: {response_count}")
                result_queue.put(None)

            except Exception as e:
                # Google STT API의 스트림 자동 종료
                # 499 CANCELLED, 500 Internal error, Unknown(요청 반복 종료) 등은 재시도
                err_text = str(e)
                if (
                    "499" in err_text
                    or "CANCELLED" in err_text.upper()
                    or "500" in err_text
                    or "Internal error" in err_text
                    or "Exception iterating requests" in err_text
                    or "StatusCode.UNKNOWN" in err_text
                ):
                    logger.info(f"[STT] 스트림 종료 (정상 또는 재시작 가능): {e}")
                else:
                    logger.error(f"[STT] Unexpected error: {e}", exc_info=True)
                result_queue.put(None)

        try:
            # Start STT processing in background thread
            stt_thread = threading.Thread(target=run_streaming_recognize, daemon=True)
            stt_thread.start()

            # Yield results as they arrive
            while True:
                # Get result from queue (with timeout to check stop event)
                try:
                    result = await asyncio.to_thread(result_queue.get, timeout=0.1)
                    if result is None:
                        break
                    yield result  # dict with transcript, is_final, confidence
                except queue.Empty:
                    if stop_event.is_set():
                        break
                    continue

        except Exception as e:
            logger.error(f"[STT] 오디오 스트림 처리 오류: {e}", exc_info=True)
            raise
        finally:
            stop_event.set()
            await transfer_task
            # Wait for STT thread to finish
            await asyncio.to_thread(stt_thread.join, timeout=5)

    async def recognize_single_audio(self, audio_bytes: bytes) -> Optional[str]:
        """단일 오디오 데이터를 인식 (비스트리밍).

        짧은 오디오 클립을 한 번에 인식합니다.
        v2 API에서는 recognize() 메서드를 사용합니다.

        Args:
            audio_bytes (bytes): 16-bit PCM 오디오 데이터

        Returns:
            Optional[str]: 인식된 텍스트. 인식 실패 시 None

        Note:
            - 최대 60초 오디오 권장
            - 실시간 용도로는 process_audio_stream() 사용 권장
            - v2에서는 batch recognition 사용 가능

        Examples:
            >>> service = STTService()
            >>> with open("audio.pcm", "rb") as f:
            ...     audio = f.read()
            >>> text = await service.recognize_single_audio(audio)
            >>> print(text)
        """
        try:
            # RecognitionConfig 생성
            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=self.language_codes,
                model=self.model,
            )

            if self.enable_automatic_punctuation:
                config.features = cloud_speech.RecognitionFeatures(
                    enable_automatic_punctuation=True
                )

            # RecognizeRequest 생성 (v2 방식)
            request = cloud_speech.RecognizeRequest(
                recognizer=self.recognizer,
                config=config,
                content=audio_bytes,
            )

            # Synchronous recognition in thread
            response = await asyncio.to_thread(self.client.recognize, request=request)

            if response.results:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"[STT] 단일 오디오 v2 인식 결과: '{transcript}'")
                return transcript

            return None

        except Exception as e:
            logger.error(f"[STT] 단일 오디오 인식 오류 (v2): {e}")
            return None
