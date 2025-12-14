"""오디오 트랙 릴레이 모듈.

WebRTC 오디오 트랙을 릴레이하고 STT 처리를 위한 프레임 캡처 기능을 제공합니다.
"""

import asyncio
import logging
from collections import deque
from typing import Optional, Deque
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
        stt_queue: Optional[asyncio.Queue] = None,
        ring_buffer: Optional[Deque] = None,
    ):
        """AudioRelayTrack 초기화.

        Args:
            track (MediaStreamTrack): 릴레이할 원본 오디오 트랙
            stt_queue (Optional[asyncio.Queue]): STT 처리용 큐 (None이면 비활성화)
            ring_buffer (Optional[Deque]): STT 재시작 시 재주입할 최신 프레임 버퍼
        """
        super().__init__()
        self.track = track
        self.stt_queue = stt_queue
        self.ring_buffer = ring_buffer

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

        # Keep a short ring buffer so we can re-feed audio when STT 재시작
        if self.ring_buffer is not None:
            self.ring_buffer.append(frame)

        # Send frame to STT queue if available
        if self.stt_queue:
            try:
                # Debug: Log first frame
                if not hasattr(self, '_first_frame_logged'):
                    logger.info("[WebRTC] AudioRelayTrack: 첫 프레임 STT 큐로 전송")
                    self._first_frame_logged = True

                self.stt_queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Drop the oldest frame to keep the most recent audio during congestion
                try:
                    dropped = self.stt_queue.get_nowait()
                    if not hasattr(self, "_drop_logged"):
                        logger.warning("[WebRTC] STT 큐 가득 참, 가장 오래된 프레임 삭제 후 최신 프레임 유지")
                        self._drop_logged = True
                    self.stt_queue.put_nowait(frame)
                except asyncio.QueueEmpty:
                    # If we cannot drop, just skip
                    logger.warning("[WebRTC] STT 큐 가득 참, 오디오 프레임 드랍")
                    pass

        return frame
