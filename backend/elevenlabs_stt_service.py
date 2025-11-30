"""ElevenLabs Speech-to-Text 실시간 스트리밍 서비스 모듈.

이 모듈은 ElevenLabs Speech-to-Text API를 사용하여 실시간 오디오 스트림을
텍스트로 변환하는 기능을 제공합니다.

주요 기능:
    - 실시간 오디오 스트림 인식 (WebSocket Streaming)
    - WebRTC 오디오 프레임을 ElevenLabs API 형식으로 변환
    - 비동기 처리를 통한 높은 처리량
    - 한국어 음성 인식 지원

Architecture:
    - ElevenLabs Scribe v2 Realtime 모델 사용
    - WebSocket 기반 실시간 스트리밍
    - AudioFrame → PCM bytes → Base64 변환 파이프라인
    - Partial/Committed transcript 지원

Examples:
    기본 사용법:
        >>> service = ElevenLabsSTTService()
        >>> async for text in service.process_audio_stream(audio_frames):
        ...     print(f"인식된 텍스트: {text}")

See Also:
    ElevenLabs STT Docs: https://elevenlabs.io/docs/capabilities/speech-to-text
"""
import asyncio
import base64
import json
import logging
import os
import time
from typing import AsyncIterator, Optional

import numpy as np
import websockets
from av import AudioFrame

logger = logging.getLogger(__name__)


class ElevenLabsSTTService:
    """ElevenLabs Speech-to-Text 실시간 스트리밍 서비스 클래스.

    WebRTC 오디오 스트림을 실시간으로 텍스트로 변환합니다.
    WebSocket 기반 Scribe v2 Realtime 모델을 사용합니다.

    Attributes:
        api_key (str): ElevenLabs API 키
        model_id (str): 사용할 STT 모델 ID
        language_code (str): 음성 인식 언어 코드
        sample_rate (int): 출력 샘플레이트 (16kHz)

    Note:
        - ELEVENLABS_API_KEY 환경 변수 필수
        - WebRTC 48kHz 오디오를 16kHz로 리샘플링
        - PCM 16-bit mono 포맷 사용
        - VAD 모드로 자동 커밋 활성화
    """

    # ElevenLabs WebSocket endpoint
    WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
    MODEL_ID = "scribe_v2_realtime"
    TARGET_SAMPLE_RATE = 16000  # ElevenLabs 권장 샘플레이트

    # VAD (Voice Activity Detection) 설정
    COMMIT_STRATEGY = "vad"  # "manual" or "vad" - VAD로 자동 커밋
    VAD_SILENCE_THRESHOLD_SECS = 0.5  # 침묵 감지 시간 (초) - 짧을수록 빠른 응답
    VAD_THRESHOLD = 0.5  # VAD 감지 임계값

    def __init__(
        self,
        api_key: Optional[str] = None,
        language_code: str = "ko",
    ):
        """ElevenLabsSTTService 초기화.

        Args:
            api_key (str, optional): ElevenLabs API 키.
                환경 변수 ELEVENLABS_API_KEY 사용 가능
            language_code (str): 음성 인식 언어 코드. 기본값 "ko" (한국어)

        Raises:
            ValueError: ELEVENLABS_API_KEY 미설정 시
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ELEVENLABS_API_KEY environment variable must be set"
            )

        self.language_code = language_code
        self.sample_rate = self.TARGET_SAMPLE_RATE

        logger.info(
            f"ElevenLabs STT Service initialized: "
            f"model={self.MODEL_ID}, "
            f"language={self.language_code}, "
            f"sample_rate={self.sample_rate}, "
            f"commit_strategy={self.COMMIT_STRATEGY}, "
            f"vad_silence={self.VAD_SILENCE_THRESHOLD_SECS}s"
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

    def _audio_frame_to_base64(self, frame: AudioFrame) -> str:
        """AudioFrame을 ElevenLabs API 형식의 Base64 문자열로 변환.

        WebRTC AudioFrame을 16-bit PCM → Base64로 변환합니다.
        48kHz → 16kHz 리샘플링도 수행합니다.

        Args:
            frame (AudioFrame): WebRTC 오디오 프레임

        Returns:
            str: Base64 인코딩된 PCM 오디오 데이터
        """
        # Convert AudioFrame to numpy array
        array = frame.to_ndarray()

        # Handle stereo to mono conversion
        if array.ndim > 1:
            array = array.flatten()

        # Check if stereo (2x samples for interleaved L-R-L-R)
        if array.size == frame.samples * 2:
            array = array.reshape(-1, 2).mean(axis=1).astype(array.dtype)

        # Convert float to int16 if needed
        if array.dtype in (np.float32, np.float64):
            array = (array * 32767).astype(np.int16)
        elif array.dtype == np.int16:
            # Apply gain to low volume audio
            max_val = np.abs(array).max()
            if max_val > 0 and max_val < 5000:
                gain = min(6500.0 / max_val, 20.0)
                array = np.clip(array * gain, -32768, 32767).astype(np.int16)

        # Resample from 48kHz to 16kHz
        if frame.sample_rate != self.TARGET_SAMPLE_RATE:
            array = self._resample_audio(array, frame.sample_rate, self.TARGET_SAMPLE_RATE)
            array = array.astype(np.int16)

        # Convert to bytes and Base64 encode
        audio_bytes = array.tobytes()
        return base64.b64encode(audio_bytes).decode('utf-8')

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
                - text (str): 인식된 텍스트
                - is_final (bool): 최종 결과 여부
                - latency_ms (float): 응답 지연시간 (밀리초)

        Note:
            - 큐에서 None을 받으면 스트림 종료
            - WebSocket 연결 실패 시 재시도
            - 0.1 ~ 1초 청크 권장 (Best Practice)
            - VAD 모드로 자동 커밋하여 committed_transcript 수신
        """
        # VAD 파라미터 포함하여 WebSocket URL 구성
        ws_url = (
            f"{self.WS_URL}"
            f"?model_id={self.MODEL_ID}"
            f"&language_code={self.language_code}"
            f"&commit_strategy={self.COMMIT_STRATEGY}"
            f"&vad_silence_threshold_secs={self.VAD_SILENCE_THRESHOLD_SECS}"
            f"&vad_threshold={self.VAD_THRESHOLD}"
        )

        extra_headers = {
            "xi-api-key": self.api_key
        }

        logger.info(f"🔌 Connecting to ElevenLabs STT WebSocket...")

        try:
            async with websockets.connect(
                ws_url,
                additional_headers=extra_headers,
                ping_interval=20,
                ping_timeout=10
            ) as ws:
                logger.info("✅ ElevenLabs WebSocket connected")

                # Wait for session_started event
                init_response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                init_data = json.loads(init_response)
                if init_data.get("message_type") == "session_started":
                    config = init_data.get("config", {})
                    vad_strategy = config.get("vad_commit_strategy", "unknown")
                    vad_silence = config.get("vad_silence_threshold_secs", "unknown")
                    logger.info(
                        f"✅ ElevenLabs session started: "
                        f"vad_commit_strategy={vad_strategy}, "
                        f"vad_silence_threshold={vad_silence}s"
                    )
                else:
                    logger.warning(f"⚠️ Unexpected init message: {init_data}")

                # Task to send audio chunks
                send_task = asyncio.create_task(
                    self._send_audio_chunks(ws, audio_queue)
                )

                # Task to receive transcripts
                try:
                    async for result in self._receive_transcripts(ws):
                        yield result
                finally:
                    send_task.cancel()
                    try:
                        await send_task
                    except asyncio.CancelledError:
                        pass

        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"❌ ElevenLabs WebSocket connection closed: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ ElevenLabs STT error: {e}", exc_info=True)
            raise

    async def _send_audio_chunks(
        self,
        ws: websockets.WebSocketClientProtocol,
        audio_queue: asyncio.Queue
    ):
        """오디오 청크를 WebSocket으로 전송합니다.

        Args:
            ws: WebSocket 연결
            audio_queue: 오디오 프레임 큐
        """
        chunk_count = 0
        accumulated_frames = []
        accumulated_duration = 0.0
        target_chunk_duration = 0.25  # 250ms 청크

        try:
            while True:
                frame = await audio_queue.get()
                if frame is None:
                    # Send remaining frames
                    if accumulated_frames:
                        await self._send_accumulated_frames(ws, accumulated_frames, chunk_count)
                    # Send commit signal
                    commit_msg = json.dumps({
                        "message_type": "input_audio_chunk",
                        "audio_base_64": "",
                        "commit": True,
                        "sample_rate": self.TARGET_SAMPLE_RATE
                    })
                    await ws.send(commit_msg)
                    logger.info(f"🏁 ElevenLabs audio stream ended. Total chunks: {chunk_count}")
                    break

                # Accumulate frames for batching
                accumulated_frames.append(frame)
                frame_duration = frame.samples / frame.sample_rate
                accumulated_duration += frame_duration

                # Send when we have enough audio (250ms chunks)
                if accumulated_duration >= target_chunk_duration:
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info("📤 Sending first audio chunk to ElevenLabs...")

                    await self._send_accumulated_frames(ws, accumulated_frames, chunk_count)

                    # Reset accumulator
                    accumulated_frames = []
                    accumulated_duration = 0.0

                    # Log progress
                    if chunk_count % 40 == 0:  # Every ~10 seconds
                        logger.info(f"📦 Sent {chunk_count} chunks to ElevenLabs")

        except asyncio.CancelledError:
            logger.info("📡 ElevenLabs audio sender cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ Error sending audio to ElevenLabs: {e}", exc_info=True)
            raise

    async def _send_accumulated_frames(
        self,
        ws: websockets.WebSocketClientProtocol,
        frames: list,
        chunk_count: int
    ):
        """누적된 프레임들을 하나의 청크로 전송합니다."""
        # Combine all frames into one audio buffer
        all_audio = []
        for frame in frames:
            array = frame.to_ndarray()
            if array.ndim > 1:
                array = array.flatten()
            if array.size == frame.samples * 2:
                array = array.reshape(-1, 2).mean(axis=1).astype(array.dtype)
            if array.dtype in (np.float32, np.float64):
                array = (array * 32767).astype(np.int16)
            elif array.dtype == np.int16:
                max_val = np.abs(array).max()
                if max_val > 0 and max_val < 5000:
                    gain = min(6500.0 / max_val, 20.0)
                    array = np.clip(array * gain, -32768, 32767).astype(np.int16)

            # Resample each frame
            if frame.sample_rate != self.TARGET_SAMPLE_RATE:
                array = self._resample_audio(array, frame.sample_rate, self.TARGET_SAMPLE_RATE)
                array = array.astype(np.int16)

            all_audio.append(array)

        # Concatenate all arrays
        combined_audio = np.concatenate(all_audio)
        audio_bytes = combined_audio.tobytes()
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        # Send to ElevenLabs
        message = json.dumps({
            "message_type": "input_audio_chunk",
            "audio_base_64": audio_base64,
            "commit": False,
            "sample_rate": self.TARGET_SAMPLE_RATE
        })
        await ws.send(message)

        if chunk_count == 1:
            logger.info(f"📤 First chunk sent: {len(audio_bytes)} bytes, {len(frames)} frames")

    async def _receive_transcripts(
        self,
        ws: websockets.WebSocketClientProtocol
    ) -> AsyncIterator[dict]:
        """WebSocket에서 transcript 메시지를 수신합니다.

        Args:
            ws: WebSocket 연결

        Yields:
            dict: 인식 결과
        """
        last_send_time = time.time()

        try:
            async for message in ws:
                receive_time = time.time()
                data = json.loads(message)
                msg_type = data.get("message_type")

                if msg_type == "partial_transcript":
                    text = data.get("text", "")
                    if text.strip():
                        latency_ms = (receive_time - last_send_time) * 1000
                        logger.debug(f"🔄 ElevenLabs partial: '{text[:50]}...' ({latency_ms:.0f}ms)")
                        yield {
                            "text": text,
                            "is_final": False,
                            "latency_ms": latency_ms,
                            "source": "elevenlabs"
                        }

                elif msg_type == "committed_transcript":
                    text = data.get("text", "")
                    if text.strip():
                        latency_ms = (receive_time - last_send_time) * 1000
                        logger.info(f"✅ ElevenLabs final: '{text}' ({latency_ms:.0f}ms)")
                        yield {
                            "text": text,
                            "is_final": True,
                            "latency_ms": latency_ms,
                            "source": "elevenlabs"
                        }

                elif msg_type == "error":
                    error_msg = data.get("error", "Unknown error")
                    logger.error(f"❌ ElevenLabs error: {error_msg}")

                # Update last send time for latency calculation
                last_send_time = time.time()

        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 ElevenLabs WebSocket closed")
        except Exception as e:
            logger.error(f"❌ Error receiving ElevenLabs transcripts: {e}", exc_info=True)
            raise
