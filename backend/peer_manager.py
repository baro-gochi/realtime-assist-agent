"""WebRTC 피어 연결 관리 모듈.

이 모듈은 WebRTC 피어 연결을 관리하고 SFU(Selective Forwarding Unit) 패턴을
구현하여 룸 기반 미디어 스트림 릴레이를 제공합니다.

주요 기능:
    - WebRTC 피어 연결 생성 및 관리
    - 오디오/비디오 트랙 릴레이 (SFU 패턴)
    - 룸 내 참가자 간 미디어 스트림 전달
    - ICE 연결 상태 모니터링
    - 오디오 프레임 캡처 (STT 처리를 위한 준비)

Architecture:
    - SFU (Selective Forwarding Unit): 서버가 미디어를 중계하여 각 클라이언트의 부하 감소
    - MediaRelay: aiortc의 미디어 릴레이를 사용한 효율적인 스트림 처리
    - Track Management: 각 피어의 오디오/비디오 트랙을 독립적으로 관리

Classes:
    AudioRelayTrack: STT 처리를 위한 오디오 프레임 캡처 기능이 있는 트랙
    VideoRelayTrack: 비디오 프레임을 릴레이하는 트랙
    PeerConnectionManager: WebRTC 연결 및 미디어 릴레이 관리

WebRTC Flow:
    1. 클라이언트가 offer 전송
    2. 서버가 RTCPeerConnection 생성
    3. 기존 참가자의 트랙을 새 참가자에게 추가
    4. answer 생성 및 반환
    5. 미디어 트랙 수신 시 다른 참가자들에게 자동 릴레이

Examples:
    기본 사용법:
        >>> manager = PeerConnectionManager()
        >>> # Offer 처리
        >>> answer = await manager.handle_offer(
        ...     peer_id="peer-123",
        ...     room_name="상담실1",
        ...     offer={"sdp": "...", "type": "offer"},
        ...     other_peers_in_room=["peer-456"]
        ... )
        >>> # 연결 종료
        >>> await manager.close_peer_connection("peer-123")

See Also:
    app.py: WebSocket 시그널링 서버
    room_manager.py: 룸 및 참가자 관리
    aiortc Documentation: https://aiortc.readthedocs.io/
"""
import asyncio
import logging
from typing import Dict, Optional, Callable, List
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from aiortc.rtcicetransport import RTCIceCandidate
from stt_service import STTService
from elevenlabs_stt_service import ElevenLabsSTTService

logger = logging.getLogger(__name__)

# STT 엔진 설정
STT_ENGINE_GOOGLE = "google"
STT_ENGINE_ELEVENLABS = "elevenlabs"
MAX_WAIT = 5.0

class AudioRelayTrack(MediaStreamTrack):
    """오디오 프레임을 릴레이하고 STT 처리를 위해 캡처하는 트랙.

    다른 참가자에게 오디오를 전달하면서 동시에 음성 인식 처리를 위한
    프레임을 STT 큐에 전달합니다. 듀얼 STT 모드에서는 두 개의 큐에 동시 전송.

    Attributes:
        kind (str): 트랙 종류 ("audio")
        track (MediaStreamTrack): 원본 오디오 트랙
        stt_queue (Optional[asyncio.Queue]): Google STT 처리를 위한 오디오 프레임 큐
        elevenlabs_queue (Optional[asyncio.Queue]): ElevenLabs STT 처리를 위한 큐

    Note:
        - 큐가 가득 차면 새 프레임은 버려짐 (오버플로우 방지)
        - stt_queue가 None이면 Google STT 처리 건너뜀
        - elevenlabs_queue가 None이면 ElevenLabs STT 처리 건너뜀

    Examples:
        >>> original_track = ... # 원본 오디오 트랙
        >>> google_queue = asyncio.Queue(maxsize=100)
        >>> elevenlabs_queue = asyncio.Queue(maxsize=100)
        >>> relay_track = AudioRelayTrack(original_track, google_queue, elevenlabs_queue)
        >>> frame = await relay_track.recv()  # 프레임 수신, 양쪽 STT 큐 전달, 릴레이
    """
    kind = "audio"

    def __init__(
        self,
        track: MediaStreamTrack,
        stt_queue: Optional[asyncio.Queue] = None,
        elevenlabs_queue: Optional[asyncio.Queue] = None
    ):
        """AudioRelayTrack 초기화.

        Args:
            track (MediaStreamTrack): 릴레이할 원본 오디오 트랙
            stt_queue (Optional[asyncio.Queue]): Google STT 처리용 큐 (None이면 비활성화)
            elevenlabs_queue (Optional[asyncio.Queue]): ElevenLabs STT 처리용 큐 (None이면 비활성화)
        """
        super().__init__()
        self.track = track
        self.stt_queue = stt_queue
        self.elevenlabs_queue = elevenlabs_queue

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

        # Send frame to Google STT queue if available
        if self.stt_queue:
            try:
                # Debug: Log first frame
                if not hasattr(self, '_first_frame_logged'):
                    logger.info("🎤 AudioRelayTrack: First frame sent to Google STT queue!")
                    self._first_frame_logged = True

                self.stt_queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Skip frame if queue is full
                logger.warning("⚠️ Google STT queue full, dropping audio frame")
                pass

        # Send frame to ElevenLabs STT queue if available
        if self.elevenlabs_queue:
            try:
                if not hasattr(self, '_first_elevenlabs_frame_logged'):
                    logger.info("🎤 AudioRelayTrack: First frame sent to ElevenLabs STT queue!")
                    self._first_elevenlabs_frame_logged = True

                self.elevenlabs_queue.put_nowait(frame)
            except asyncio.QueueFull:
                logger.warning("⚠️ ElevenLabs STT queue full, dropping audio frame")
                pass

        return frame


class VideoRelayTrack(MediaStreamTrack):
    """비디오 프레임을 릴레이하는 트랙.

    참가자로부터 받은 비디오 스트림을 다른 참가자들에게 전달합니다.
    AudioRelayTrack과 달리 프레임 캡처 기능은 없습니다.

    Attributes:
        kind (str): 트랙 종류 ("video")
        track (MediaStreamTrack): 원본 비디오 트랙

    Examples:
        >>> original_track = ... # 원본 비디오 트랙
        >>> relay_track = VideoRelayTrack(original_track)
        >>> frame = await relay_track.recv()  # 프레임 수신 및 릴레이
    """
    kind = "video"

    def __init__(self, track: MediaStreamTrack):
        """VideoRelayTrack 초기화.

        Args:
            track (MediaStreamTrack): 릴레이할 원본 비디오 트랙
        """
        super().__init__()
        self.track = track

    async def recv(self):
        """비디오 프레임을 수신하고 릴레이합니다.

        원본 트랙에서 프레임을 받아 그대로 전달합니다.

        Returns:
            VideoFrame: 수신한 비디오 프레임
        """
        return await self.track.recv()


class PeerConnectionManager:
    """WebRTC 피어 연결을 룸 기반으로 관리하는 클래스.

    SFU(Selective Forwarding Unit) 패턴을 구현하여 서버가 미디어를 중계합니다.
    같은 룸의 피어들 간 미디어 스트림을 효율적으로 전달합니다.

    Attributes:
        peers (Dict[str, RTCPeerConnection]): 피어 ID → RTCPeerConnection 매핑
        peer_rooms (Dict[str, str]): 피어 ID → 룸 이름 매핑
        relay (MediaRelay): aiortc 미디어 릴레이 객체
        audio_tracks (Dict[str, AudioRelayTrack]): 피어 ID → 오디오 트랙 매핑
        video_tracks (Dict[str, VideoRelayTrack]): 피어 ID → 비디오 트랙 매핑

    Architecture Pattern:
        SFU (Selective Forwarding Unit):
            - 각 클라이언트는 서버에만 연결 (1:1)
            - 서버가 미디어를 선택적으로 다른 피어들에게 전달
            - 클라이언트 부하 감소 (N-1개 연결 대신 1개)
            - 서버에서 미디어 처리/분석 가능 (STT 등)

    WebRTC Connection Lifecycle:
        1. create_peer_connection(): 새 피어 연결 생성
        2. on("track"): 미디어 트랙 수신 시 자동 릴레이
        3. handle_offer(): offer 처리 및 answer 생성
        4. close_peer_connection(): 연결 종료 및 정리

    Examples:
        >>> manager = PeerConnectionManager()
        >>> # 피어 연결 처리
        >>> answer = await manager.handle_offer(
        ...     peer_id="peer-123",
        ...     room_name="상담실1",
        ...     offer={"sdp": "v=0\\r\\n...", "type": "offer"},
        ...     other_peers_in_room=["peer-456", "peer-789"]
        ... )
        >>> # 모든 연결 정리
        >>> await manager.cleanup_all()
    """

    def __init__(self):
        """PeerConnectionManager 초기화.

        빈 피어 딕셔너리와 미디어 릴레이를 생성합니다.
        """
        # peer_id -> RTCPeerConnection
        self.peers: Dict[str, RTCPeerConnection] = {}

        # peer_id -> room_name
        self.peer_rooms: Dict[str, str] = {}

        # Media relay (kept for future STT processing)
        self.relay = MediaRelay()

        # peer_id -> tracks (now storing original tracks for direct relay)
        self.audio_tracks: Dict[str, MediaStreamTrack] = {}
        self.video_tracks: Dict[str, MediaStreamTrack] = {}

        # Callback for track received event (used to trigger renegotiation)
        self.on_track_received_callback = None

        # Callback for ICE candidate event (used to send backend candidates to client)
        self.on_ice_candidate_callback = None

        # Track which peers have already triggered renegotiation (to avoid multiple triggers)
        self.renegotiation_triggered: Dict[str, bool] = {}

        # STT service instances per peer (peer_id -> STTService)
        # Each peer needs its own STT service for independent streaming
        self.stt_services: Dict[str, STTService] = {}
        self.on_transcript_callback: Optional[Callable[[str, str, str, str], None]] = None  # peer_id, room, text, source

        # Audio processing queues for Google STT (peer_id -> Queue)
        self.audio_queues: Dict[str, asyncio.Queue] = {}

        # STT processing tasks (peer_id -> Task)
        self.stt_tasks: Dict[str, asyncio.Task] = {}

        # ElevenLabs STT 관련 속성
        self.elevenlabs_stt_services: Dict[str, ElevenLabsSTTService] = {}
        self.elevenlabs_audio_queues: Dict[str, asyncio.Queue] = {}
        self.elevenlabs_stt_tasks: Dict[str, asyncio.Task] = {}
        self.dual_stt_enabled: Dict[str, bool] = {}  # peer_id -> dual STT 활성화 여부

        # Audio consumer tasks to prevent garbage collection (peer_id -> List[Task])
        self.audio_consumer_tasks: Dict[str, List[asyncio.Task]] = {}

        # Track TURN candidate arrival (peer_id -> bool)
        self.turn_candidate_received: Dict[str, bool] = {}

    async def create_peer_connection(
        self,
        peer_id: str,
        room_name: str,
        other_peers_in_room: list
    ) -> RTCPeerConnection:
        logger.info(f"▶ create_peer_connection: peer={peer_id[:8]}, room={room_name}, others={len(other_peers_in_room)}")
        """룸의 피어를 위한 새로운 WebRTC 연결을 생성합니다.

        RTCPeerConnection을 생성하고 이벤트 핸들러를 등록합니다.
        ICE 연결 상태 변경과 미디어 트랙 수신을 처리합니다.

        Args:
            peer_id (str): 연결을 생성할 피어의 ID
            room_name (str): 피어가 속한 룸 이름
            other_peers_in_room (list): 같은 룸의 다른 피어 ID 리스트

        Returns:
            RTCPeerConnection: 생성된 WebRTC 피어 연결 객체

        Event Handlers:
            - iceconnectionstatechange: ICE 연결 상태 변경 모니터링
                - "failed" 상태 시 자동으로 연결 종료
            - track: 미디어 트랙 수신 시
                - 오디오: AudioRelayTrack 생성 및 룸 내 릴레이
                - 비디오: VideoRelayTrack 생성 및 룸 내 릴레이
                - track.on("ended"): 트랙 종료 이벤트 처리

        Note:
            - 생성된 연결은 self.peers에 저장됨
            - 룸 정보는 self.peer_rooms에 저장됨
            - 수신된 트랙은 자동으로 같은 룸의 다른 피어들에게 릴레이됨

        Examples:
            >>> manager = PeerConnectionManager()
            >>> pc = await manager.create_peer_connection(
            ...     peer_id="peer-123",
            ...     room_name="상담실1",
            ...     other_peers_in_room=["peer-456"]
            ... )
            >>> print(pc.iceConnectionState)
            new
        """
        # ICE 서버 설정 (STUN/TURN)
        from aiortc import RTCConfiguration, RTCIceServer
        import os

        # AWS coturn 서버 설정 (Static credentials)
        turn_server_url = os.getenv("TURN_SERVER_URL")
        turn_username = os.getenv("TURN_USERNAME")
        turn_credential = os.getenv("TURN_CREDENTIAL")
        stun_server_url = os.getenv("STUN_SERVER_URL")

        ice_servers = []

        # STUN 서버 추가 (AWS coturn + Google 백업)
        if stun_server_url:
            ice_servers.append(RTCIceServer(urls=[stun_server_url]))
            logger.info(f"✅ AWS STUN server configured: {stun_server_url}")

        # Google STUN 서버 (백업용)
        ice_servers.append(RTCIceServer(urls=["stun:stun.l.google.com:19302"]))

        # TURN 서버 추가 (AWS coturn)
        if turn_server_url and turn_username and turn_credential:
            ice_servers.append(RTCIceServer(
                urls=[turn_server_url],
                username=turn_username,
                credential=turn_credential
            ))
            logger.info(f"✅ AWS TURN server configured: {turn_server_url}")
            logger.debug(f"TURN credentials - username: {turn_username}")
        else:
            logger.warning("⚠️ AWS TURN server credentials not found in .env - using STUN only")

        # aiortc doesn't support iceTransportPolicy parameter
        # Use both TURN (preferred) and STUN (fallback) servers
        config = RTCConfiguration(iceServers=ice_servers)

        # CRITICAL: Set bundlePolicy to force ICE to wait for all candidates
        # This prevents gathering from completing before TURN is ready
        pc = RTCPeerConnection(configuration=config)

        # Force ICE gathering to wait by NOT calling setLocalDescription immediately
        logger.info(f"  🔧 RTCPeerConnection created, TURN will allocate in background")
        self.peers[peer_id] = pc
        self.peer_rooms[peer_id] = room_name

        @pc.on("icecandidate")
        async def on_ice_candidate(candidate):
            """ICE candidate 생성 시 호출되는 이벤트 핸들러."""
            if candidate:
                is_relay = "relay" in candidate.candidate.lower()
                cand_type = "TURN" if is_relay else "host/srflx"
                logger.info(f"  🔔 ICE candidate: type={cand_type}, peer={peer_id[:8]}")

                if is_relay:
                    self.turn_candidate_received[peer_id] = True

                if self.on_ice_candidate_callback:
                    await self.on_ice_candidate_callback(peer_id, candidate)
                else:
                    logger.warning(f"  ⚠️ Callback is None!")

        @pc.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():
            """ICE 연결 상태 변경 시 호출되는 이벤트 핸들러.

            WebRTC의 ICE (Interactive Connectivity Establishment) 연결 상태를
            모니터링하고, 연결 실패 시 자동으로 피어 연결을 종료합니다.

            Note:
                - 상태 변경은 로그에 기록됨
                - "failed" 상태 시 자동으로 연결 종료 및 정리 수행
                - ICE 상태: new, checking, connected, completed, failed, disconnected, closed
            """
            logger.info(f"Peer {peer_id} ICE state: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                await self.close_peer_connection(peer_id)

        @pc.on("track")
        async def on_track(track: MediaStreamTrack):
            """미디어 트랙 수신 시 호출되는 이벤트 핸들러.

            WebRTC 연결을 통해 새로운 미디어 트랙(오디오 또는 비디오)이
            수신되면 자동으로 호출되며, 트랙을 저장하고 같은 룸의 다른
            피어들에게 릴레이합니다.

            Args:
                track (MediaStreamTrack): 수신된 미디어 트랙

            Workflow:
                1. 트랙 종류 확인 (audio/video)
                2. 원본 트랙 저장 (self.audio_tracks 또는 self.video_tracks)
                3. 같은 룸의 다른 피어들에게 트랙 릴레이
                4. 첫 번째 트랙인 경우 renegotiation 콜백 트리거
                5. 트랙 종료 이벤트 핸들러 등록

            Note:
                - 피어당 첫 번째 트랙 수신 시에만 renegotiation 트리거
                - 트랙은 디코딩/인코딩 없이 원본 그대로 전달 (낮은 지연시간)
                - 각 트랙에 "ended" 이벤트 핸들러 등록
            """
            logger.info(f"Peer {peer_id} in room '{room_name}' received {track.kind} track")

            # Check if this is the first track from this peer
            trigger_renegotiation = peer_id not in self.renegotiation_triggered

            if track.kind == "audio":
                # Start STT processing for this peer if not already started
                if peer_id not in self.stt_tasks:
                    await self._start_stt_processing(peer_id, room_name)

                # Get STT queue for this peer
                stt_queue = self.audio_queues.get(peer_id)

                # Get ElevenLabs STT queue if dual STT is enabled
                elevenlabs_queue = self.elevenlabs_audio_queues.get(peer_id)

                # Create AudioRelayTrack with STT queues (Google + ElevenLabs if enabled)
                relay_track = AudioRelayTrack(track, stt_queue, elevenlabs_queue)

                # Store relay track (instead of original track)
                self.audio_tracks[peer_id] = relay_track

                # IMPORTANT: Start consuming this track immediately for STT
                # Even if no other peers are in the room, we need to consume the track
                # to get frames for STT processing
                consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, relay_track))
                # Store task to prevent it from being garbage collected
                if peer_id not in self.audio_consumer_tasks:
                    self.audio_consumer_tasks[peer_id] = []
                self.audio_consumer_tasks[peer_id].append(consumer_task)

                # Add relay track to other peers in same room
                await self._relay_to_room_peers(peer_id, room_name, relay_track)

            elif track.kind == "video":
                # Store original track (no decoding/re-encoding)
                self.video_tracks[peer_id] = track

                # Add track to other peers in same room
                await self._relay_to_room_peers(peer_id, room_name, track)

            # Trigger renegotiation ONCE per peer (when first track arrives)
            if trigger_renegotiation and self.on_track_received_callback:
                self.renegotiation_triggered[peer_id] = True
                logger.info(f"🔔 Triggering renegotiation for peer {peer_id} (first track)")
                await self.on_track_received_callback(peer_id, room_name, track.kind)
            elif not trigger_renegotiation:
                logger.info(f"⏭️ Skipping renegotiation trigger (already triggered for {peer_id})")

            @track.on("ended")
            async def on_ended():
                """트랙 종료 시 호출되는 이벤트 핸들러.

                미디어 트랙의 스트리밍이 종료되었을 때 호출됩니다.
                참가자가 카메라/마이크를 끄거나 연결이 종료될 때 발생합니다.

                Note:
                    - 현재는 로깅만 수행
                    - 향후 트랙 종료 시 추가 정리 작업 가능
                """
                logger.info(f"Peer {peer_id} {track.kind} track ended")

        return pc

    async def _relay_to_room_peers(
        self,
        source_peer_id: str,
        room_name: str,
        track: MediaStreamTrack
    ):
        """같은 룸의 다른 모든 피어에게 미디어 트랙을 릴레이합니다.

        소스 피어에서 받은 미디어 트랙을 같은 룸의 다른 모든 피어의
        RTCPeerConnection에 추가하여 미디어 스트림을 전달합니다.

        Args:
            source_peer_id (str): 미디어를 전송하는 피어의 ID
            room_name (str): 릴레이할 룸 이름
            track (MediaStreamTrack): 릴레이할 미디어 트랙 (오디오 또는 비디오)

        Note:
            - 소스 피어는 제외됨 (본인에게는 전송하지 않음)
            - 같은 룸의 피어만 대상
            - 연결이 닫힌 피어는 제외됨
            - 각 릴레이 동작은 로그에 기록됨

        Examples:
            >>> # 내부적으로 on("track") 핸들러에서 호출됨
            >>> await self._relay_to_room_peers(
            ...     source_peer_id="peer-123",
            ...     room_name="상담실1",
            ...     track=audio_relay_track
            ... )
            INFO:__main__:Relaying audio from peer-123 to peer-456 in room '상담실1'
        """
        for peer_id, pc in self.peers.items():
            # Only relay to peers in same room, excluding source peer
            if (peer_id != source_peer_id and
                self.peer_rooms.get(peer_id) == room_name and
                pc.connectionState != "closed"):
                pc.addTrack(track)
                logger.info(f"Relaying {track.kind} from {source_peer_id} to {peer_id} in room '{room_name}'")

    async def handle_offer(
        self,
        peer_id: str,
        room_name: str,
        offer: dict,
        other_peers_in_room: list
    ) -> dict:
        logger.info(f"▶ handle_offer: peer={peer_id[:8]}, room={room_name}")
        """WebRTC offer를 처리하고 answer를 생성합니다.

        클라이언트로부터 받은 WebRTC offer를 처리하여 피어 연결을 설정하고,
        기존 참가자의 미디어 트랙을 추가한 후 answer를 반환합니다.

        Args:
            peer_id (str): offer를 보낸 피어의 ID
            room_name (str): 피어가 참가한 룸 이름
            offer (dict): WebRTC offer 데이터
                - sdp (str): Session Description Protocol
                - type (str): "offer"
            other_peers_in_room (list): 같은 룸의 다른 피어 ID 리스트

        Returns:
            dict: WebRTC answer 데이터
                - sdp (str): Session Description Protocol
                - type (str): "answer"

        Workflow:
            1. 피어 연결 생성 또는 재사용 (renegotiation case)
            2. 같은 룸의 다른 피어들의 트랙을 새 피어에게 추가
                - 기존 오디오 트랙 추가
                - 기존 비디오 트랙 추가
            3. Remote Description 설정 (offer)
            4. Answer 생성
            5. Local Description 설정 (answer)
            6. Answer 반환

        Note:
            - Renegotiation case: 기존 연결이 있으면 재사용 (트랙 유지)
            - Initial connection case: 새 연결 생성 후 트랙 추가
            - 기존 참가자가 없으면 트랙 추가 단계는 건너뜀
            - 각 트랙 추가는 로그에 기록됨
            - SDP 교환을 통해 WebRTC 연결이 완성됨

        Examples:
            >>> manager = PeerConnectionManager()
            >>> offer_data = {
            ...     "sdp": "v=0\\r\\no=- 123456 2 IN IP4 127.0.0.1\\r\\n...",
            ...     "type": "offer"
            ... }
            >>> answer = await manager.handle_offer(
            ...     peer_id="peer-123",
            ...     room_name="상담실1",
            ...     offer=offer_data,
            ...     other_peers_in_room=["peer-456", "peer-789"]
            ... )
            >>> print(answer["type"])
            answer
        """
        # Check if this is a renegotiation (peer connection already exists)
        if peer_id in self.peers:
            pc = self.peers[peer_id]
            logger.info(f"🔄 Renegotiating existing connection for {peer_id}")

            # Get currently added track IDs to avoid duplicates
            current_senders = pc.getSenders()
            current_track_ids = {sender.track.id for sender in current_senders if sender.track}
            logger.info(f"Current tracks in connection: {len(current_track_ids)}")

            # IMPORTANT: Set remote description FIRST before adding tracks
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
            )

            # NOW add NEW tracks from other peers (skip already added tracks)
            tracks_added = 0
            for other_peer_id in other_peers_in_room:
                if other_peer_id != peer_id:
                    # Add audio track if exists and not already added
                    if other_peer_id in self.audio_tracks:
                        track = self.audio_tracks[other_peer_id]
                        if track.id not in current_track_ids:
                            pc.addTrack(track)
                            logger.info(f"🔄 Added NEW audio track from {other_peer_id} to {peer_id}")
                            tracks_added += 1
                        else:
                            logger.info(f"⏭️ Skipped existing audio track from {other_peer_id}")

                    # Add video track if exists and not already added
                    if other_peer_id in self.video_tracks:
                        track = self.video_tracks[other_peer_id]
                        if track.id not in current_track_ids:
                            pc.addTrack(track)
                            logger.info(f"🔄 Added NEW video track from {other_peer_id} to {peer_id}")
                            tracks_added += 1
                        else:
                            logger.info(f"⏭️ Skipped existing video track from {other_peer_id}")

            logger.info(f"Total new tracks added: {tracks_added}")

            # Wait for TURN BEFORE creating answer
            logger.info(f"  ⏳ [Renego] Waiting {MAX_WAIT}s for TURN...")
            await asyncio.sleep(MAX_WAIT)
            logger.info(f"  ✅ [Renego] TURN ready")

            # Create answer (includes newly added tracks)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Log ICE gathering state
            candidate_count = pc.localDescription.sdp.count("a=candidate:")
            logger.info(f"  📊 [Renego] After setLocalDescription: gathering={pc.iceGatheringState}, candidates={candidate_count}")

            return {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }

        # Initial connection case - create new peer connection
        logger.info(f"🆕 Creating new peer connection for {peer_id}")
        pc = await self.create_peer_connection(peer_id, room_name, other_peers_in_room)

        # Add tracks from other peers in the room
        for other_peer_id in other_peers_in_room:
            if other_peer_id != peer_id:
                # Add audio track if exists
                if other_peer_id in self.audio_tracks:
                    pc.addTrack(self.audio_tracks[other_peer_id])
                    logger.info(f"Added audio track from {other_peer_id} to {peer_id}")

                # Add video track if exists
                if other_peer_id in self.video_tracks:
                    pc.addTrack(self.video_tracks[other_peer_id])
                    logger.info(f"Added video track from {other_peer_id} to {peer_id}")

        # Set remote description (offer)
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        )

        # Create answer
        logger.info(f"  📝 Creating answer...")
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        candidate_count = pc.localDescription.sdp.count("a=candidate:")
        logger.info(f"  📊 SDP has {candidate_count} candidates, gathering={pc.iceGatheringState}")

        # NOTE: aiortc doesn't fire on("icecandidate") for candidates after gathering completes
        # TURN allocation happens in background but won't trigger events
        # We just send the answer - client will use STUN/host candidates
        # Connection should still work via STUN reflexive candidates
        logger.info(f"  ✅ Sending answer (TURN may complete later)")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }

    async def close_peer_connection(self, peer_id: str):
        """피어 연결을 종료하고 관련 리소스를 정리합니다.

        RTCPeerConnection을 닫고 모든 관련 데이터를 딕셔너리에서 제거합니다.
        미디어 트랙도 함께 정리됩니다.

        Args:
            peer_id (str): 종료할 피어의 ID

        Cleanup Steps:
            1. RTCPeerConnection 종료 (pc.close())
            2. peers 딕셔너리에서 제거
            3. peer_rooms 딕셔너리에서 제거
            4. audio_tracks 딕셔너리에서 제거
            5. video_tracks 딕셔너리에서 제거
            6. renegotiation_triggered 플래그 제거

        Note:
            - 존재하지 않는 피어 ID로 호출해도 안전함
            - 연결 종료는 로그에 기록됨
            - 메모리 누수 방지를 위해 모든 참조 제거

        Examples:
            >>> manager = PeerConnectionManager()
            >>> # ... 피어 연결 생성 및 사용 ...
            >>> await manager.close_peer_connection("peer-123")
            INFO:__main__:Peer peer-123 connection closed
        """
        if peer_id in self.peers:
            pc = self.peers[peer_id]
            await pc.close()
            del self.peers[peer_id]

        if peer_id in self.peer_rooms:
            del self.peer_rooms[peer_id]

        if peer_id in self.audio_tracks:
            del self.audio_tracks[peer_id]

        if peer_id in self.video_tracks:
            del self.video_tracks[peer_id]

        if peer_id in self.renegotiation_triggered:
            del self.renegotiation_triggered[peer_id]

        # Cancel audio consumer tasks
        if peer_id in self.audio_consumer_tasks:
            for task in self.audio_consumer_tasks[peer_id]:
                if not task.done():
                    task.cancel()
            del self.audio_consumer_tasks[peer_id]

        # Stop STT processing
        await self._stop_stt_processing(peer_id)

        logger.info(f"Peer {peer_id} connection closed")

    async def cleanup_all(self):
        """모든 피어 연결을 종료합니다.

        서버 종료 시 호출되어 모든 활성 WebRTC 연결을 정리합니다.
        각 피어에 대해 close_peer_connection()을 순차적으로 호출합니다.

        Note:
            - lifespan 이벤트의 shutdown 단계에서 호출됨
            - 모든 리소스가 안전하게 해제됨
            - 연결이 많을 경우 시간이 걸릴 수 있음

        Examples:
            >>> manager = PeerConnectionManager()
            >>> # 서버 종료 시
            >>> await manager.cleanup_all()
        """
        peer_ids = list(self.peers.keys())
        for peer_id in peer_ids:
            await self.close_peer_connection(peer_id)

    def get_peer_connection(self, peer_id: str) -> Optional[RTCPeerConnection]:
        """피어의 RTCPeerConnection을 반환합니다."""
        return self.peers.get(peer_id)

    def get_peer_room(self, peer_id: str) -> Optional[str]:
        """피어가 속한 룸의 이름을 반환합니다.

        Args:
            peer_id (str): 조회할 피어의 ID

        Returns:
            Optional[str]: 피어가 속한 룸 이름.
                          피어가 어떤 룸에도 속하지 않으면 None

        Examples:
            >>> manager = PeerConnectionManager()
            >>> # ... handle_offer로 피어 생성 ...
            >>> room = manager.get_peer_room("peer-123")
            >>> print(room)
            상담실1
        """
        return self.peer_rooms.get(peer_id)

    async def _consume_audio_track(self, peer_id: str, track: AudioRelayTrack):
        """오디오 트랙을 consume하여 STT 처리를 활성화합니다.

        AudioRelayTrack의 recv()를 계속 호출하여 프레임을 소비합니다.
        이렇게 해야 WebRTC가 계속 프레임을 전송하고, STT queue에 프레임이 들어갑니다.

        Args:
            peer_id (str): 피어 ID
            track (AudioRelayTrack): Consume할 오디오 트랙

        Note:
            - 트랙이 종료되거나 에러 발생 시 자동으로 종료됩니다
            - 피어가 연결 해제되면 자동으로 정리됩니다
        """
        logger.info(f"🎧 Starting audio track consumer for peer {peer_id}")
        frame_count = 0
        try:
            while True:
                # Consume frame from track (this triggers AudioRelayTrack.recv())
                frame = await track.recv()
                frame_count += 1

                if frame_count == 1:
                    logger.info(f"✅ First frame consumed from peer {peer_id}")
                elif frame_count % 500 == 0:
                    logger.debug(f"Consumed {frame_count} frames from peer {peer_id}")

        except asyncio.CancelledError:
            logger.info(f"📡 Audio consumer task cancelled for peer {peer_id}")
        except Exception as e:
            logger.error(f"❌ Audio track consumer error for peer {peer_id}: {type(e).__name__}: {e}", exc_info=True)
        finally:
            logger.info(f"🏁 Audio track consumer ended for peer {peer_id}. Total frames: {frame_count}")

    async def _start_stt_processing(self, peer_id: str, room_name: str):
        """피어의 오디오 스트림에 대한 STT 처리를 시작합니다.

        오디오 프레임 큐를 생성하고 STT 처리 태스크를 시작합니다.
        각 피어는 독립적인 STTService 인스턴스를 가집니다.
        듀얼 STT 모드에서는 ElevenLabs STT도 병렬로 시작합니다.

        Args:
            peer_id (str): STT를 시작할 피어의 ID
            room_name (str): 피어가 속한 룸 이름

        Note:
            - 피어당 하나의 STT 처리 태스크만 실행됨
            - 각 피어는 독립적인 Google STT API 스트림을 가짐
            - 듀얼 모드 시 ElevenLabs STT도 병렬 실행
            - 인식된 텍스트는 on_transcript_callback으로 전달됨
        """
        if peer_id in self.stt_tasks:
            logger.warning(f"STT already running for peer {peer_id}")
            return

        # Create dedicated STTService instance for this peer (Google)
        stt_service = STTService()
        self.stt_services[peer_id] = stt_service

        # Create audio queue for this peer (Google STT)
        # Increased from 100 to 500 to prevent overflow during STT restarts
        # 48kHz audio = ~50 frames/sec, so 500 frames = ~10 seconds buffer
        audio_queue = asyncio.Queue(maxsize=500)
        self.audio_queues[peer_id] = audio_queue

        # Start Google STT processing task
        task = asyncio.create_task(
            self._process_stt_for_peer(peer_id, room_name, audio_queue, stt_service)
        )
        self.stt_tasks[peer_id] = task

        logger.info(f"🎤 Started Google STT processing for peer {peer_id} in room '{room_name}'")

        # Start ElevenLabs STT if dual mode is enabled for this peer
        if self.dual_stt_enabled.get(peer_id, False):
            await self._start_elevenlabs_stt_processing(peer_id, room_name)

    async def _start_elevenlabs_stt_processing(self, peer_id: str, room_name: str):
        """피어의 ElevenLabs STT 처리를 시작합니다.

        Args:
            peer_id (str): STT를 시작할 피어의 ID
            room_name (str): 피어가 속한 룸 이름
        """
        import os
        if peer_id in self.elevenlabs_stt_tasks:
            logger.warning(f"ElevenLabs STT already running for peer {peer_id}")
            return

        # Check if API key is available
        if not os.getenv("ELEVENLABS_API_KEY"):
            logger.warning("⚠️ ELEVENLABS_API_KEY not set, skipping ElevenLabs STT")
            return

        try:
            # Create ElevenLabs STT service instance
            elevenlabs_service = ElevenLabsSTTService()
            self.elevenlabs_stt_services[peer_id] = elevenlabs_service

            # Create audio queue for ElevenLabs STT
            elevenlabs_queue = asyncio.Queue(maxsize=500)
            self.elevenlabs_audio_queues[peer_id] = elevenlabs_queue

            # Start ElevenLabs STT processing task
            task = asyncio.create_task(
                self._process_elevenlabs_stt_for_peer(peer_id, room_name, elevenlabs_queue, elevenlabs_service)
            )
            self.elevenlabs_stt_tasks[peer_id] = task

            logger.info(f"🎤 Started ElevenLabs STT processing for peer {peer_id} in room '{room_name}'")
        except Exception as e:
            logger.error(f"❌ Failed to start ElevenLabs STT for peer {peer_id}: {e}")

    async def _process_elevenlabs_stt_for_peer(
        self,
        peer_id: str,
        room_name: str,
        audio_queue: asyncio.Queue,
        stt_service: ElevenLabsSTTService
    ):
        """피어의 오디오 스트림을 ElevenLabs STT로 처리합니다.

        Args:
            peer_id (str): 처리할 피어의 ID
            room_name (str): 피어가 속한 룸 이름
            audio_queue (asyncio.Queue): 오디오 프레임 큐
            stt_service (ElevenLabsSTTService): ElevenLabs STT 서비스 인스턴스
        """
        retry_count = 0
        max_retries = 100

        while retry_count < max_retries:
            try:
                logger.info(f"🎤 Starting ElevenLabs STT stream #{retry_count + 1} for peer {peer_id}")

                async for result in stt_service.process_audio_stream(audio_queue):
                    text = result.get("text", "")
                    is_final = result.get("is_final", False)
                    latency_ms = result.get("latency_ms", 0)

                    if text.strip():
                        logger.info(f"💬 ElevenLabs transcript from peer {peer_id}: {text} (is_final={is_final}, latency: {latency_ms:.0f}ms)")

                        # Call callback for both partial and final results
                        if self.on_transcript_callback:
                            # Pass is_final flag to distinguish partial vs final
                            await self.on_transcript_callback(
                                peer_id, room_name, text, STT_ENGINE_ELEVENLABS, is_final
                            )

                # Stream ended normally - restart
                logger.info(f"🔄 ElevenLabs STT stream ended for peer {peer_id}, restarting...")
                await asyncio.sleep(0.2)

                # Create new service instance
                stt_service = ElevenLabsSTTService()
                self.elevenlabs_stt_services[peer_id] = stt_service
                continue

            except asyncio.CancelledError:
                logger.info(f"ElevenLabs STT processing cancelled for peer {peer_id}")
                raise

            except Exception as e:
                retry_count += 1
                logger.error(f"❌ ElevenLabs STT error for peer {peer_id} (attempt {retry_count}): {e}")

                # Clear queue before retrying
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                await asyncio.sleep(1)

                # Create new service instance
                try:
                    stt_service = ElevenLabsSTTService()
                    self.elevenlabs_stt_services[peer_id] = stt_service
                except Exception:
                    pass
                continue

        logger.error(f"❌ Max ElevenLabs STT retries reached for peer {peer_id}")

    async def _process_stt_for_peer(
        self,
        peer_id: str,
        room_name: str,
        audio_queue: asyncio.Queue,
        stt_service: STTService
    ):
        """피어의 오디오 스트림을 STT로 처리합니다.

        오디오 큐에서 프레임을 읽어 Google STT API로 전송하고
        인식 결과를 콜백으로 전달합니다.

        Google STT v2 스트리밍 제한사항 대응:
        - 스트림이 타임아웃되면 자동으로 재시도
        - 각 스트림은 약 25초 후 자동 재시작 (타임아웃 방지)

        Args:
            peer_id (str): 처리할 피어의 ID
            room_name (str): 피어가 속한 룸 이름
            audio_queue (asyncio.Queue): 오디오 프레임 큐
            stt_service (STTService): 이 피어 전용 STT 서비스 인스턴스

        Note:
            - 무한 루프로 계속 처리됨 (연결 종료 시 취소)
            - 각 피어는 독립적인 STT 스트림을 사용
            - 스트림 타임아웃 시 자동 재시도
        """
        retry_count = 0
        max_retries = 100  # 연결이 끊길 때까지 계속 재시도

        while retry_count < max_retries:
            try:
                logger.info(f"🎤 Starting STT stream #{retry_count + 1} for peer {peer_id}")

                async for result in stt_service.process_audio_stream(audio_queue):
                    transcript = result.get("transcript", "")
                    is_final = result.get("is_final", True)
                    confidence = result.get("confidence", 0.0)

                    result_type = "FINAL" if is_final else "INTERIM"
                    logger.info(f"💬 Google STT {result_type} from peer {peer_id}: {transcript} (confidence: {confidence:.2f})")

                    # Call callback if set (with source identifier and is_final flag)
                    if self.on_transcript_callback and transcript.strip():
                        await self.on_transcript_callback(peer_id, room_name, transcript, STT_ENGINE_GOOGLE, is_final)

                # Stream ended normally - restart it for continuous recognition
                logger.info(f"🔄 STT stream ended normally for peer {peer_id}, restarting for continuous recognition...")

                # 큐에 남은 프레임 유지 (버퍼링) - 새 스트림에서 처리
                queue_size = audio_queue.qsize()
                if queue_size > 0:
                    logger.info(f"📦 Preserving {queue_size} buffered frames for new stream")

                # 빠르게 재시작 (지연 최소화)
                await asyncio.sleep(0.05)

                # Create new STT service for fresh stream
                stt_service = STTService()
                self.stt_services[peer_id] = stt_service
                continue  # Restart the loop instead of breaking

            except asyncio.CancelledError:
                logger.info(f"STT processing cancelled for peer {peer_id}")
                raise

            except Exception as e:
                retry_count += 1
                error_msg = str(e)

                # Check if it's a timeout error
                if "timeout" in error_msg.lower() or "409" in error_msg:
                    logger.warning(
                        f"⏱️ STT stream timeout for peer {peer_id} "
                        f"(attempt {retry_count}/{max_retries}). "
                        f"Restarting stream..."
                    )

                    # CRITICAL: Clear the queue to prevent overflow
                    # The old frames are stale and will cause the new stream to timeout too
                    queue_size = audio_queue.qsize()
                    if queue_size > 0:
                        logger.info(f"🧹 Clearing {queue_size} stale frames from audio queue")
                        while not audio_queue.empty():
                            try:
                                audio_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                    # Wait a bit before retrying
                    await asyncio.sleep(0.5)

                    # Create new STT service instance to reset stream
                    stt_service = STTService()
                    self.stt_services[peer_id] = stt_service
                    continue
                else:
                    # Other errors - log and retry
                    logger.error(
                        f"Error in STT processing for peer {peer_id}: {e}",
                        exc_info=True
                    )
                    await asyncio.sleep(1)
                    continue

        if retry_count >= max_retries:
            logger.error(f"❌ Max STT retries reached for peer {peer_id}")

    async def _stop_stt_processing(self, peer_id: str):
        """피어의 STT 처리를 중지합니다.

        STT 처리 태스크를 취소하고 오디오 큐 및 STT 서비스를 정리합니다.
        Google STT와 ElevenLabs STT 모두 정리합니다.

        Args:
            peer_id (str): STT를 중지할 피어의 ID
        """
        # Cancel Google STT task
        if peer_id in self.stt_tasks:
            task = self.stt_tasks[peer_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.stt_tasks[peer_id]

        # Clear Google audio queue
        if peer_id in self.audio_queues:
            # Send None to signal end of stream
            try:
                await self.audio_queues[peer_id].put(None)
            except asyncio.QueueFull:
                pass
            del self.audio_queues[peer_id]

        # Remove Google STT service instance
        if peer_id in self.stt_services:
            del self.stt_services[peer_id]

        # Cancel ElevenLabs STT task
        if peer_id in self.elevenlabs_stt_tasks:
            task = self.elevenlabs_stt_tasks[peer_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.elevenlabs_stt_tasks[peer_id]

        # Clear ElevenLabs audio queue
        if peer_id in self.elevenlabs_audio_queues:
            try:
                await self.elevenlabs_audio_queues[peer_id].put(None)
            except asyncio.QueueFull:
                pass
            del self.elevenlabs_audio_queues[peer_id]

        # Remove ElevenLabs STT service instance
        if peer_id in self.elevenlabs_stt_services:
            del self.elevenlabs_stt_services[peer_id]

        # Clear dual STT flag
        if peer_id in self.dual_stt_enabled:
            del self.dual_stt_enabled[peer_id]

        logger.info(f"🛑 Stopped all STT processing for peer {peer_id}")

    async def enable_dual_stt(self, peer_id: str, room_name: str, enabled: bool = True):
        """피어의 듀얼 STT 모드를 활성화/비활성화합니다.

        활성화 시 ElevenLabs STT도 병렬로 처리합니다.
        비활성화 시 ElevenLabs STT를 중지합니다.

        Args:
            peer_id (str): 대상 피어 ID
            room_name (str): 피어가 속한 룸 이름
            enabled (bool): 듀얼 STT 활성화 여부
        """
        self.dual_stt_enabled[peer_id] = enabled

        if enabled:
            # Start ElevenLabs STT if not already running
            if peer_id not in self.elevenlabs_stt_tasks:
                await self._start_elevenlabs_stt_processing(peer_id, room_name)

            # CRITICAL: Update existing AudioRelayTrack with the new queue
            # Without this, audio frames won't be sent to ElevenLabs
            if peer_id in self.audio_tracks and peer_id in self.elevenlabs_audio_queues:
                audio_track = self.audio_tracks[peer_id]
                if isinstance(audio_track, AudioRelayTrack):
                    audio_track.elevenlabs_queue = self.elevenlabs_audio_queues[peer_id]
                    logger.info(f"🔗 Connected ElevenLabs queue to AudioRelayTrack for peer {peer_id}")

            logger.info(f"✅ Dual STT enabled for peer {peer_id}")
        else:
            # Disconnect queue from AudioRelayTrack first
            if peer_id in self.audio_tracks:
                audio_track = self.audio_tracks[peer_id]
                if isinstance(audio_track, AudioRelayTrack):
                    audio_track.elevenlabs_queue = None
                    logger.info(f"🔌 Disconnected ElevenLabs queue from AudioRelayTrack for peer {peer_id}")

            # Stop ElevenLabs STT
            if peer_id in self.elevenlabs_stt_tasks:
                task = self.elevenlabs_stt_tasks[peer_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.elevenlabs_stt_tasks[peer_id]

            if peer_id in self.elevenlabs_audio_queues:
                try:
                    await self.elevenlabs_audio_queues[peer_id].put(None)
                except asyncio.QueueFull:
                    pass
                del self.elevenlabs_audio_queues[peer_id]

            if peer_id in self.elevenlabs_stt_services:
                del self.elevenlabs_stt_services[peer_id]

            logger.info(f"⏹️ Dual STT disabled for peer {peer_id}")
