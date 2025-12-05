"""오디오 트랙 릴레이 모듈.

WebRTC 오디오 트랙을 릴레이하고 STT 처리를 위한 프레임 캡처 기능을 제공합니다.
"""

import asyncio
import logging
from typing import Optional
from aiortc import MediaStreamTrack

logger = logging.getLogger(__name__)


class AudioRelayTrack(MediaStreamTrack):
    """오디오 프레임을 릴레이하고 STT 처리를 위해 캡처하는 트랙.

    다른 참가자에게 오디오를 전달하면서 동시에 음성 인식 처리를 위한
    프레임을 STT 큐에 전달합니다.

    Attributes:
        kind (str): 트랙 종류 ("audio")
        track (MediaStreamTrack): 원본 오디오 트랙
        stt_queue (Optional[asyncio.Queue]): STT 처리를 위한 오디오 프레임 큐

    Note:
        - 큐가 가득 차면 새 프레임은 버려짐 (오버플로우 방지)
        - stt_queue가 None이면 STT 처리 건너뜀

    Examples:
        >>> original_track = ... # 원본 오디오 트랙
        >>> stt_queue = asyncio.Queue(maxsize=100)
        >>> relay_track = AudioRelayTrack(original_track, stt_queue)
        >>> frame = await relay_track.recv()  # 프레임 수신, STT 큐 전달, 릴레이
    """
    kind = "audio"

    def __init__(
        self,
        track: MediaStreamTrack,
        stt_queue: Optional[asyncio.Queue] = None
    ):
        """AudioRelayTrack 초기화.

        Args:
            track (MediaStreamTrack): 릴레이할 원본 오디오 트랙
            stt_queue (Optional[asyncio.Queue]): STT 처리용 큐 (None이면 비활성화)
        """
        super().__init__()
        self.track = track
        self.stt_queue = stt_queue

    async def recv(self):
        """오디오 프레임을 수신하고 릴레이합니다.

        원본 트랙에서 프레임을 받아 STT 처리를 위해 큐에 저장한 후
        다른 참가자에게 전달합니다.

        Returns:
            AudioFrame: 수신한 오디오 프레임

        Note:
            - 큐가 가득 차면 QueueFull 예외를 무시하고 프레임을 버림
            - 프레임은 항상 반환되어 릴레이 기능은 유지됨
        """
        frame = await self.track.recv()

        # Send frame to STT queue if available
        if self.stt_queue:
            try:
                # Debug: Log first frame
                if not hasattr(self, '_first_frame_logged'):
                    logger.info("🎤 AudioRelayTrack: First frame sent to STT queue!")
                    self._first_frame_logged = True

                self.stt_queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Skip frame if queue is full
                logger.warning("⚠️ STT queue full, dropping audio frame")
                pass

        return frame
