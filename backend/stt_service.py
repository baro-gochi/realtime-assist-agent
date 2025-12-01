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
    peer_manager.py: 오디오 프레임 캡처
    app.py: WebSocket을 통한 결과 전송
    Google Cloud Speech-to-Text V2 Documentation:
        https://cloud.google.com/speech-to-text/v2/docs
"""
import asyncio
import logging
import os
from typing import AsyncIterator, Optional, List
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.api_core.client_options import ClientOptions
from google.protobuf.duration_pb2 import Duration
from av import AudioFrame
import numpy as np
import queue
import threading

logger = logging.getLogger(__name__)

# Google STT 최적화 상수
TARGET_SAMPLE_RATE = 16000  # ElevenLabs와 동일하게 16kHz
TARGET_CHUNK_DURATION = 0.25  # 250ms 청크 (ElevenLabs와 동일)


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
        enable_interim_results (bool): 중간 결과 활성화 여부

    Note:
        - GOOGLE_APPLICATION_CREDENTIALS 환경 변수 필수
        - GOOGLE_CLOUD_PROJECT 환경 변수 필수 (프로젝트 ID)
        - WebRTC 오디오는 자동으로 인코딩 감지됨
        - 25KB 스트림 제한 주의

    Examples:
        >>> service = STTService()
        >>> # 오디오 스트림 처리
        >>> async for transcript in service.process_audio_stream(audio_queue):
        ...     print(f"인식 결과: {transcript}")
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        language_codes: Optional[List[str]] = None,
        model: Optional[str] = None,
        enable_automatic_punctuation: Optional[bool] = None,
        enable_interim_results: Optional[bool] = None,
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
            enable_interim_results (bool, optional): 중간 결과 활성화.
                환경 변수 STT_ENABLE_INTERIM_RESULTS 또는 False 사용

        Raises:
            ValueError: GOOGLE_CLOUD_PROJECT 미설정 시

        Note:
            - .env 파일에서 환경 변수 로드 필요
            - 서비스 계정 키 파일 권한 확인 필요
            - v2 API는 Recognizer 개념 필수
        """
        # Google Cloud 인증 및 프로젝트 확인 프로젝트 ID (v2에서 필수)
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            logger.warning(
                "GOOGLE_APPLICATION_CREDENTIALS not set. "
                "STT service may not work properly."
            )
            
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable must be set for v2 API"
            )

        # Configuration from environment or defaults
        default_language = os.getenv("STT_LANGUAGE_CODE", "ko-KR")
        self.language_codes = language_codes or [default_language]

        self.model = model or os.getenv("STT_MODEL", "short")
        self.sample_rate = TARGET_SAMPLE_RATE
        self.input_sample_rate = int(os.getenv("STT_SAMPLE_RATE_HERTZ", "32000"))  # WebRTC 입력 샘플레이트 (32kbps 비트레이트에 최적화)

        # Location 설정 (리전별 엔드포인트 지원)
        self.location = os.getenv("STT_LOCATION", "global")

        # Regional endpoint 설정
        if self.location != "global":
            api_endpoint = f"{self.location}-speech.googleapis.com"
            client_options = ClientOptions(api_endpoint=api_endpoint)
            self.client = SpeechClient(client_options=client_options)
            logger.info(f"🌏 Using regional endpoint: {api_endpoint}")
        else:
            self.client = SpeechClient()
            logger.info("🌐 Using global endpoint: speech.googleapis.com")

        # Recognizer path
        self.recognizer = f"projects/{self.project_id}/locations/{self.location}/recognizers/_"

        self.enable_automatic_punctuation = (
            enable_automatic_punctuation
            if enable_automatic_punctuation is not None
            else os.getenv("STT_ENABLE_AUTOMATIC_PUNCTUATION", "true").lower() == "true"
        )

        # Enable interim results for real-time partial transcript display
        self.enable_interim_results = (
            enable_interim_results
            if enable_interim_results is not None
            else os.getenv("STT_ENABLE_INTERIM_RESULTS", "true").lower() == "true"
        )

        logger.info(
            f"STT Service v2 initialized: "
            f"project={self.project_id}, "
            f"location={self.location}, "
            f"languages={self.language_codes}, "
            f"model={self.model}, "
            f"sample_rate={self.sample_rate}Hz, "
            f"punctuation={self.enable_automatic_punctuation}, "
            f"interim={self.enable_interim_results}"
        )

    def _resample_audio(self, audio_array: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """오디오를 목표 샘플레이트로 리샘플링합니다.

        간단한 선형 보간 방식을 사용합니다.

        Args:
            audio_array: 원본 오디오 배열
            orig_sr: 원본 샘플레이트
            target_sr: 목표 샘플레이트

        Returns:
            리샘플링된 오디오 배열
        """
        if orig_sr == target_sr:
            return audio_array

        # 리샘플링 비율 계산
        ratio = target_sr / orig_sr
        new_length = int(len(audio_array) * ratio)

        # 선형 보간으로 리샘플링
        indices = np.linspace(0, len(audio_array) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)

        return resampled.astype(audio_array.dtype)

    def _create_streaming_config(self) -> cloud_speech.StreamingRecognitionConfig:
        """스트리밍 인식을 위한 Google STT v2 설정 생성.

        Returns:
            cloud_speech.StreamingRecognitionConfig: 스트리밍 인식 설정 객체

        Note:
            - ExplicitDecodingConfig: WebRTC 오디오 형식 명시적 지정
            - language_codes: 다중 언어 지원 (리스트)
            - model: latest_long 등
            - interim_results: 실시간 중간 결과 (False 권장 - 낮은 지연시간)
        """
        recognition_config = cloud_speech.RecognitionConfig(
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
            recognition_config.features = cloud_speech.RecognitionFeatures(
                enable_automatic_punctuation=True
            )

        # StreamingRecognitionConfig 생성
        streaming_config = cloud_speech.StreamingRecognitionConfig(
            config=recognition_config,
        )

        # StreamingRecognitionFeatures 추가 (interim results + voice activity timeout)
        streaming_config.streaming_features = cloud_speech.StreamingRecognitionFeatures(
            interim_results=self.enable_interim_results,
            enable_voice_activity_events=True,
            voice_activity_timeout=cloud_speech.StreamingRecognitionFeatures.VoiceActivityTimeout(
                speech_end_timeout=Duration(seconds=59),  # 발화 후 59초까지 스트림 유지
            ),
        )

        return streaming_config

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
        streaming_config = self._create_streaming_config()

        # Thread-safe queue to bridge asyncio and sync code
        sync_queue = queue.Queue()
        stop_event = threading.Event()

        # Background task to transfer frames from asyncio queue to sync queue
        async def transfer_frames():
            """asyncio Queue에서 thread-safe Queue로 프레임 전송"""
            chunk_count = 0
            try:
                logger.info("🎧 Starting frame transfer task...")
                while not stop_event.is_set():
                    frame = await audio_queue.get()
                    if frame is None:
                        logger.info("Audio stream ended (received None)")
                        sync_queue.put(None)
                        break

                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info(f"✅ First audio frame received! Starting transfer...")
                    if chunk_count % 50 == 0:
                        logger.info(f"📦 Processing audio chunk #{chunk_count}")

                    sync_queue.put(frame)
                logger.info(f"Frame transfer completed. Total chunks: {chunk_count}")
            except Exception as e:
                logger.error(f"Error in frame transfer: {e}", exc_info=True)
                sync_queue.put(None)

        # Start frame transfer task
        transfer_task = asyncio.create_task(transfer_frames())

        def generate_requests():
            """동기 요청 생성기 (v2 방식) - 250ms 청크 누적 전송"""
            # First request with recognizer and config
            logger.info("📤 Sending initial config request to STT API...")
            config_request = cloud_speech.StreamingRecognizeRequest(
                recognizer=self.recognizer,
                streaming_config=streaming_config,
            )
            yield config_request
            logger.info("✅ Config request sent, waiting for audio frames...")

            # 🔧 ElevenLabs와 동일한 청크 누적 방식
            frame_count = 0
            chunk_count = 0
            accumulated_arrays = []
            accumulated_duration = 0.0
            last_frame_time = None
            silence_threshold = 30.0
            first_frame_timeout = 60.0

            def process_accumulated_chunks():
                """누적된 오디오를 처리하여 전송"""
                nonlocal chunk_count
                if not accumulated_arrays:
                    return None

                # 모든 배열을 하나로 합침
                combined_array = np.concatenate(accumulated_arrays)

                # 48kHz → 16kHz 리샘플링 (ElevenLabs와 동일)
                resampled = self._resample_audio(combined_array, self.input_sample_rate, self.sample_rate)
                resampled = resampled.astype(np.int16)

                chunk_count += 1
                if chunk_count == 1:
                    logger.info(f"📤 First 250ms chunk: {len(combined_array)} samples @ 48kHz → {len(resampled)} samples @ 16kHz")

                audio_bytes = resampled.tobytes()
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
                            logger.info(f"⏱️ No audio for {silence_duration:.1f}s, closing stream gracefully...")
                            break
                    elif frame_count == 0:
                        # No frames received at all after long wait
                        logger.error(f"❌ No audio frames received after {first_frame_timeout}s timeout!")
                        break
                    continue

                if frame is None:
                    # 스트림 종료 전 남은 오디오 전송
                    if accumulated_arrays:
                        audio_bytes = process_accumulated_chunks()
                        if audio_bytes:
                            yield cloud_speech.StreamingRecognizeRequest(audio=audio_bytes)
                    logger.info(f"🏁 Stream end signal received. Total frames: {frame_count}, chunks sent: {chunk_count}")
                    break

                # Update last frame time
                import time
                last_frame_time = time.time()

                frame_count += 1
                if frame_count == 1:
                    logger.info(f"🔍 AudioFrame info - sample_rate: {frame.sample_rate}, format: {frame.format.name}, samples: {frame.samples}")

                # Convert frame to numpy array
                array = frame.to_ndarray()

                # 🔧 Handle stereo to mono conversion
                if array.ndim > 1:
                    array = array.flatten()

                if array.size == frame.samples * 2:
                    array = array.reshape(-1, 2).mean(axis=1).astype(array.dtype)
                    if frame_count == 1:
                        logger.info(f"🔧 Converted stereo to mono")

                # 🔧 Handle audio format conversion
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

                # 250ms 이상 누적되면 전송 (ElevenLabs와 동일)
                if accumulated_duration >= TARGET_CHUNK_DURATION:
                    audio_bytes = process_accumulated_chunks()
                    if audio_bytes:
                        chunk_size = len(audio_bytes)
                        if chunk_size > 25000:
                            logger.warning(f"Audio chunk size {chunk_size} exceeds 25KB limit, splitting...")
                            for i in range(0, len(audio_bytes), self.input_sample_rate):
                                chunk = audio_bytes[i:i+self.input_sample_rate]
                                yield cloud_speech.StreamingRecognizeRequest(audio=chunk)
                        else:
                            yield cloud_speech.StreamingRecognizeRequest(audio=audio_bytes)

                        if chunk_count % 40 == 0:  # ~10초마다 로그
                            logger.info(f"📦 Sent {chunk_count} chunks to Google STT")

                    # 누적 초기화
                    accumulated_arrays = []
                    accumulated_duration = 0.0

        # Result queue to get transcripts from thread
        result_queue = queue.Queue()

        def run_streaming_recognize():
            """동기 STT 호출을 스레드에서 실행"""
            try:
                logger.info(f"🎙️ Starting streaming recognition with recognizer: {self.recognizer}")
                logger.info(f"🔗 API endpoint: {self.client._transport._host if hasattr(self.client, '_transport') else 'unknown'}")

                logger.info("📡 Calling streaming_recognize()...")
                responses_iterator = self.client.streaming_recognize(
                    requests=generate_requests()
                )
                logger.info("📡 streaming_recognize() returned iterator, starting to iterate...")

                logger.info("⏳ Waiting for first response from STT API...")

                response_count = 0
                for response in responses_iterator:
                    if response_count == 0:
                        logger.info("✅ STT stream connection established, first response received!")
                    else:
                        logger.info(f"⏳ Received response after waiting...")
                    response_count += 1
                    logger.info(f"📨 Received response #{response_count} from STT API")

                    if not response.results:
                        logger.info(f"📭 Response #{response_count} has no results (empty)")
                        continue

                    result = response.results[0]
                    logger.info(f"📬 Response #{response_count}: is_final={result.is_final}, alternatives={len(result.alternatives) if result.alternatives else 0}")

                    if result.is_final or self.enable_interim_results:
                        if result.alternatives:
                            transcript = result.alternatives[0].transcript
                            confidence = result.alternatives[0].confidence if result.is_final else 0.0

                            result_type = "FINAL" if result.is_final else "INTERIM"
                            logger.info(
                                f"STT Result ({result_type}): '{transcript}' "
                                f"(confidence: {confidence:.2f})"
                            )

                            # Send both final and interim results with is_final flag
                            result_queue.put({
                                "transcript": transcript,
                                "is_final": result.is_final,
                                "confidence": confidence
                            })

                    logger.info(f"⏳ Waiting for response #{response_count + 1}...")

                # Signal end of stream
                logger.info(f"🏁 Response iterator ended. Total responses: {response_count}")
                result_queue.put(None)

            except Exception as e:
                # Google STT API의 스트림 자동 종료 (정상적인 동작)
                # 499 CANCELLED: Google이 스트림을 자동으로 닫음
                # 500 Internal error: 스트림 제한 시간 도달
                if ("499" in str(e) or "CANCELLED" in str(e).upper() or
                    "500" in str(e) or "Internal error" in str(e)):
                    logger.info(f"🔄 STT stream ended (normal behavior), will restart: {e}")
                else:
                    logger.error(f"❌ Unexpected STT error: {e}", exc_info=True)
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
            logger.error(f"Error in process_audio_stream: {e}", exc_info=True)
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
                logger.info(f"Single audio STT v2 result: '{transcript}'")
                return transcript

            return None

        except Exception as e:
            logger.error(f"Error in single audio recognition (v2): {e}")
            return None
