"""WebRTC 피어 연결 관리 모듈.

이 모듈은 WebRTC 피어 연결을 관리하고 SFU(Selective Forwarding Unit) 패턴을
구현하여 룸 기반 오디오 스트림 릴레이를 제공합니다.

주요 기능:
    - WebRTC 피어 연결 생성 및 관리
    - 오디오 트랙 릴레이 (SFU 패턴)
    - 룸 내 참가자 간 오디오 스트림 전달
    - ICE 연결 상태 모니터링
    - 오디오 프레임 캡처 (STT 처리를 위한 준비)

Architecture:
    - SFU (Selective Forwarding Unit): 서버가 오디오를 중계하여 각 클라이언트의 부하 감소
    - MediaRelay: aiortc의 미디어 릴레이를 사용한 효율적인 스트림 처리
    - Track Management: 각 피어의 오디오 트랙을 독립적으로 관리

Classes:
    PeerConnectionManager: WebRTC 연결 및 오디오 릴레이 관리

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
    room_manager.py: 룸 및 참가자 관리
    aiortc Documentation: https://aiortc.readthedocs.io/
"""
import asyncio
import logging
from collections import deque
from typing import Dict, Optional, Callable, List, Deque
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay

from .tracks import AudioRelayTrack
from .config import connection_config
from ..stt import STTService

logger = logging.getLogger(__name__)


class PeerConnectionManager:
    """WebRTC 피어 연결을 룸 기반으로 관리하는 클래스.

    SFU(Selective Forwarding Unit) 패턴을 구현하여 서버가 오디오를 중계합니다.
    같은 룸의 피어들 간 오디오 스트림을 효율적으로 전달합니다.

    Attributes:
        peers (Dict[str, RTCPeerConnection]): 피어 ID → RTCPeerConnection 매핑
        peer_rooms (Dict[str, str]): 피어 ID → 룸 이름 매핑
        relay (MediaRelay): aiortc 미디어 릴레이 객체
        audio_tracks (Dict[str, AudioRelayTrack]): 피어 ID → 오디오 트랙 매핑

    Architecture Pattern:
        SFU (Selective Forwarding Unit):
            - 각 클라이언트는 서버에만 연결 (1:1)
            - 서버가 오디오를 선택적으로 다른 피어들에게 전달
            - 클라이언트 부하 감소 (N-1개 연결 대신 1개)
            - 서버에서 오디오 처리/분석 가능 (STT 등)

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

        # Callback for track received event (used to trigger renegotiation)
        self.on_track_received_callback = None

        # Callback for ICE candidate event (used to send backend candidates to client)
        self.on_ice_candidate_callback = None

        # Track which peers have already triggered renegotiation (to avoid multiple triggers)
        self.renegotiation_triggered: Dict[str, bool] = {}

        # STT service instances per peer (peer_id -> STTService)
        # Each peer needs its own STT service for independent streaming
        self.stt_services: Dict[str, STTService] = {}
        self.on_transcript_callback: Optional[Callable[[str, str, str, str, bool], None]] = None  # peer_id, room, text, source, is_final

        # Audio processing queues for STT (peer_id -> Queue)
        self.audio_queues: Dict[str, asyncio.Queue] = {}

        # STT processing tasks (peer_id -> Task)
        self.stt_tasks: Dict[str, asyncio.Task] = {}

        # Audio consumer tasks to prevent garbage collection (peer_id -> List[Task])
        self.audio_consumer_tasks: Dict[str, List[asyncio.Task]] = {}

        # Track TURN candidate arrival (peer_id -> bool)
        self.turn_candidate_received: Dict[str, bool] = {}

        # Short ring buffers per peer to re-inject audio across STT restarts
        self.audio_ring_buffers: Dict[str, Deque] = {}

    async def create_peer_connection(
        self,
        peer_id: str,
        room_name: str,
        other_peers_in_room: list
    ) -> RTCPeerConnection:
        logger.info(f"[WebRTC] 피어 연결 생성: peer={peer_id[:8]}, room={room_name}, 다른참가자={len(other_peers_in_room)}")
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
            - track: 오디오 트랙 수신 시
                - 오디오: AudioRelayTrack 생성 및 룸 내 릴레이
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
        from .config import ice_config

        ice_servers = []

        # STUN 서버 추가 (AWS coturn + Google 백업)
        if ice_config.STUN_SERVER_URL:
            ice_servers.append(RTCIceServer(urls=[ice_config.STUN_SERVER_URL]))
            logger.info(f"[WebRTC] AWS STUN 서버 설정: {ice_config.STUN_SERVER_URL}")

        # Google STUN 서버 (백업용)
        for stun_url in ice_config.DEFAULT_STUN_SERVERS:
            ice_servers.append(RTCIceServer(urls=[stun_url]))

        # TURN 서버 추가 (AWS coturn)
        if ice_config.has_turn_server:
            ice_servers.append(RTCIceServer(
                urls=[ice_config.TURN_SERVER_URL],
                username=ice_config.TURN_USERNAME,
                credential=ice_config.TURN_CREDENTIAL
            ))
            logger.info(f"[WebRTC] AWS TURN 서버 설정: {ice_config.TURN_SERVER_URL}")
            logger.debug(f"[WebRTC] TURN 자격증명 - username: {ice_config.TURN_USERNAME}")
        else:
            logger.warning("[WebRTC] AWS TURN 서버 설정 없음 - STUN만 사용")

        # aiortc doesn't support iceTransportPolicy parameter
        # Use both TURN (preferred) and STUN (fallback) servers
        config = RTCConfiguration(iceServers=ice_servers)

        # CRITICAL: Set bundlePolicy to force ICE to wait for all candidates
        # This prevents gathering from completing before TURN is ready
        pc = RTCPeerConnection(configuration=config)

        # Force ICE gathering to wait by NOT calling setLocalDescription immediately
        logger.info(f"[WebRTC] RTCPeerConnection 생성 완료, TURN 백그라운드 할당")
        self.peers[peer_id] = pc
        self.peer_rooms[peer_id] = room_name

        @pc.on("icecandidate")
        async def on_ice_candidate(candidate):
            """ICE candidate 생성 시 호출되는 이벤트 핸들러."""
            if candidate:
                is_relay = "relay" in candidate.candidate.lower()
                cand_type = "TURN" if is_relay else "host/srflx"
                logger.info(f"[WebRTC] ICE 후보: type={cand_type}, peer={peer_id[:8]}")

                if is_relay:
                    self.turn_candidate_received[peer_id] = True

                if self.on_ice_candidate_callback:
                    await self.on_ice_candidate_callback(peer_id, candidate)
                else:
                    logger.warning(f"[WebRTC] 콜백이 None입니다!")

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
            logger.info(f"[WebRTC] 피어 {peer_id[:8]} ICE 상태: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                await self.close_peer_connection(peer_id)

        @pc.on("track")
        async def on_track(track: MediaStreamTrack):
            """오디오 트랙 수신 시 호출되는 이벤트 핸들러.

            WebRTC 연결을 통해 새로운 오디오 트랙이 수신되면 자동으로 호출되며,
            트랙을 저장하고 같은 룸의 다른 피어들에게 릴레이합니다.

            Args:
                track (MediaStreamTrack): 수신된 오디오 트랙

            Workflow:
                1. 오디오 트랙인지 확인
                2. MediaRelay를 통해 트랙 복제 (각 소비자에게 독립적인 스트림 제공)
                3. STT용 트랙과 릴레이용 트랙을 별도로 생성
                4. 첫 번째 트랙인 경우 renegotiation 콜백 트리거
                5. 트랙 종료 이벤트 핸들러 등록

            Note:
                - 피어당 첫 번째 트랙 수신 시에만 renegotiation 트리거
                - MediaRelay.subscribe()로 각 소비자에게 독립적인 프레임 스트림 제공
                - 이렇게 해야 RTP timestamp가 일정하게 유지됨 (jitterBufferDelay 안정화)
                - 각 트랙에 "ended" 이벤트 핸들러 등록
            """
            logger.info(f"[WebRTC] 피어 {peer_id[:8]} (룸: {room_name}) {track.kind} 트랙 수신")

            # Check if this is the first track from this peer
            trigger_renegotiation = peer_id not in self.renegotiation_triggered

            if track.kind == "audio":
                # Start STT processing for this peer if not already started
                if peer_id not in self.stt_tasks:
                    await self._start_stt_processing(peer_id, room_name)

                # Get STT queue and ring buffer for this peer
                stt_queue = self.audio_queues.get(peer_id)
                ring_buffer = self.audio_ring_buffers.get(peer_id)

                # CRITICAL FIX: Use MediaRelay.subscribe() to create independent track copies
                # Without this, multiple consumers (STT + other peers) share the same frame buffer,
                # causing RTP timestamp discontinuities and jitterBufferDelay to increase continuously.

                # 1. Create STT track using relay subscription
                stt_track_source = self.relay.subscribe(track)
                stt_relay_track = AudioRelayTrack(stt_track_source, stt_queue, ring_buffer)

                # 2. Store original track for relay to other peers (each will get their own subscription)
                self.audio_tracks[peer_id] = track

                # 3. Start consuming STT track for speech recognition
                consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, stt_relay_track))
                # Store task to prevent it from being garbage collected
                if peer_id not in self.audio_consumer_tasks:
                    self.audio_consumer_tasks[peer_id] = []
                self.audio_consumer_tasks[peer_id].append(consumer_task)

                # 4. Add relay track to other peers in same room (each gets independent subscription)
                await self._relay_to_room_peers(peer_id, room_name, track)

            # Trigger renegotiation ONCE per peer (when first track arrives)
            if trigger_renegotiation and self.on_track_received_callback:
                self.renegotiation_triggered[peer_id] = True
                logger.info(f"[WebRTC] 피어 {peer_id[:8]} renegotiation 트리거 (첫 트랙)")
                await self.on_track_received_callback(peer_id, room_name, track.kind)
            elif not trigger_renegotiation:
                logger.info(f"[WebRTC] renegotiation 스킵 (피어 {peer_id[:8]} 이미 트리거됨)")

            @track.on("ended")
            async def on_ended():
                """트랙 종료 시 호출되는 이벤트 핸들러.

                오디오 트랙의 스트리밍이 종료되었을 때 호출됩니다.
                참가자가 마이크를 끄거나 연결이 종료될 때 발생합니다.

                Note:
                    - 현재는 로깅만 수행
                    - 향후 트랙 종료 시 추가 정리 작업 가능
                """
                logger.info(f"[WebRTC] 피어 {peer_id[:8]} {track.kind} 트랙 종료")

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
            track (MediaStreamTrack): 릴레이할 원본 미디어 트랙 (오디오 또는 비디오)

        Note:
            - 소스 피어는 제외됨 (본인에게는 전송하지 않음)
            - 같은 룸의 피어만 대상
            - 연결이 닫힌 피어는 제외됨
            - 각 피어에게 MediaRelay.subscribe()로 독립적인 트랙 복사본 전달
            - 이렇게 해야 RTP timestamp가 일정하게 유지됨 (jitterBufferDelay 안정화)
            - 각 릴레이 동작은 로그에 기록됨

        Examples:
            >>> # 내부적으로 on("track") 핸들러에서 호출됨
            >>> await self._relay_to_room_peers(
            ...     source_peer_id="peer-123",
            ...     room_name="상담실1",
            ...     track=original_audio_track
            ... )
            INFO:__main__:Relaying audio from peer-123 to peer-456 in room '상담실1'
        """
        for peer_id, pc in self.peers.items():
            # Only relay to peers in same room, excluding source peer
            if (peer_id != source_peer_id and
                self.peer_rooms.get(peer_id) == room_name and
                pc.connectionState != "closed"):
                # MediaRelay.subscribe() for independent frame buffer per peer
                relayed_track = self.relay.subscribe(track)
                pc.addTrack(relayed_track)
                logger.info(f"[WebRTC] {track.kind} 릴레이: {source_peer_id[:8]} -> {peer_id[:8]} (룸: {room_name})")

    async def handle_offer(
        self,
        peer_id: str,
        room_name: str,
        offer: dict,
        other_peers_in_room: list
    ) -> dict:
        logger.info(f"[WebRTC] offer 처리: peer={peer_id[:8]}, room={room_name}")
        """WebRTC offer를 처리하고 answer를 생성합니다.

        클라이언트로부터 받은 WebRTC offer를 처리하여 피어 연결을 설정하고,
        기존 참가자의 오디오 트랙을 추가한 후 answer를 반환합니다.

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
            2. 같은 룸의 다른 피어들의 오디오 트랙을 새 피어에게 추가
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
            logger.info(f"[WebRTC] 기존 연결 재협상: {peer_id[:8]}")

            # Get currently added track IDs to avoid duplicates
            current_senders = pc.getSenders()
            logger.info(f"[WebRTC] 재협상: 상태 - signaling={pc.signalingState}, connection={pc.connectionState}")
            logger.info(f"[WebRTC] 현재 센더 수: {len(current_senders)}")
            current_track_ids = set()
            for sender in current_senders:
                if sender.track:
                    track_id = sender.track.id
                    if track_id is not None:
                        current_track_ids.add(track_id)
                        logger.debug(f"[WebRTC] 센더 트랙: {track_id}")
                    else:
                        logger.warning(f"[WebRTC] 센더 트랙 ID가 None")
                else:
                    logger.debug(f"[WebRTC] 센더에 트랙 없음")
            logger.info(f"[WebRTC] 연결 내 트랙 수: {len(current_track_ids)}")

            # CRITICAL FIX: Do NOT add tracks during renegotiation!
            # Adding tracks after setRemoteDescription causes "None is not in list" error
            # in aiortc's createAnswer() because the transceiver matching fails.
            # Tracks from other peers will be relayed through the on("track") handler
            # when their media arrives.

            # Set remote description first
            try:
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
                )
            except Exception as sdp_error:
                logger.error(f"[WebRTC] 재협상 중 remote description 설정 실패: {sdp_error}")
                raise

            logger.info(f"[WebRTC] setRemoteDescription 후: signaling={pc.signalingState}")

            # If state is already stable, setRemoteDescription handled the offer internally
            # This can happen when aiortc determines no actual changes are needed
            if pc.signalingState == "stable":
                logger.info(f"[WebRTC] 시그널링 이미 stable - answer 불필요, 현재 local description 반환")
                # Return the existing local description (already has answer set)
                if pc.localDescription:
                    return {
                        "sdp": pc.localDescription.sdp,
                        "type": "answer"
                    }
                else:
                    # Edge case: no local description, need to create one
                    logger.warning("[WebRTC] stable 상태이나 local description 없음, answer 생성 불가")
                    raise ValueError("Cannot create answer: signaling state is stable but no local description")

            # CRITICAL: Create answer IMMEDIATELY - do not wait!
            # The signaling state can change during async waits, causing "None is not in list" errors
            # ICE gathering will happen asynchronously after answer is created
            logger.info(f"[WebRTC] answer 즉시 생성 (signaling={pc.signalingState})")

            # Create answer (includes newly added tracks)
            try:
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                logger.info(f"[WebRTC] answer 생성 및 local description 설정 완료")
            except Exception as answer_error:
                logger.error(f"[WebRTC] 재협상 중 answer 생성/설정 실패: {answer_error}")
                logger.error(f"[WebRTC] PC 상태: signaling={pc.signalingState}, connection={pc.connectionState}")
                raise

            # Log ICE gathering state
            candidate_count = pc.localDescription.sdp.count("a=candidate:")
            logger.info(f"[WebRTC] 재협상 setLocalDescription 후: gathering={pc.iceGatheringState}, 후보수={candidate_count}")

            return {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }

        # Initial connection case - create new peer connection
        logger.info(f"[WebRTC] 새 피어 연결 생성: {peer_id[:8]}")
        pc = await self.create_peer_connection(peer_id, room_name, other_peers_in_room)

        # Add audio tracks from other peers in the room
        for other_peer_id in other_peers_in_room:
            if other_peer_id != peer_id:
                # Add audio track if exists
                if other_peer_id in self.audio_tracks:
                    original_track = self.audio_tracks[other_peer_id]
                    # MediaRelay.subscribe() for independent frame buffer
                    relayed_track = self.relay.subscribe(original_track)
                    pc.addTrack(relayed_track)
                    logger.info(f"[WebRTC] 오디오 트랙 추가: {other_peer_id[:8]} -> {peer_id[:8]}")

        # Set remote description (offer)
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        )

        # Create answer
        logger.info(f"[WebRTC] answer 생성 중...")
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        candidate_count = pc.localDescription.sdp.count("a=candidate:")
        logger.info(f"[WebRTC] SDP 후보 수: {candidate_count}, gathering={pc.iceGatheringState}")

        # NOTE: aiortc doesn't fire on("icecandidate") for candidates after gathering completes
        # TURN allocation happens in background but won't trigger events
        # We just send the answer - client will use STUN/host candidates
        # Connection should still work via STUN reflexive candidates
        logger.info(f"[WebRTC] answer 전송 (TURN은 나중에 완료될 수 있음)")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }

    async def close_peer_connection(self, peer_id: str):
        """피어 연결을 종료하고 관련 리소스를 정리합니다.

        RTCPeerConnection을 닫고 모든 관련 데이터를 딕셔너리에서 제거합니다.
        오디오 트랙도 함께 정리됩니다.

        Args:
            peer_id (str): 종료할 피어의 ID

        Cleanup Steps:
            1. RTCPeerConnection 종료 (pc.close())
            2. peers 딕셔너리에서 제거
            3. peer_rooms 딕셔너리에서 제거
            4. audio_tracks 딕셔너리에서 제거
            5. renegotiation_triggered 플래그 제거

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

        logger.info(f"[WebRTC] 피어 {peer_id[:8]} 연결 종료")

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
        logger.info(f"[WebRTC] 피어 {peer_id[:8]} 오디오 트랙 컨슈머 시작")
        frame_count = 0
        try:
            while True:
                # Consume frame from track (this triggers AudioRelayTrack.recv())
                frame = await track.recv()
                frame_count += 1

                if frame_count == 1:
                    logger.info(f"[WebRTC] 피어 {peer_id[:8]} 첫 프레임 수신")
                elif frame_count % 500 == 0:
                    logger.debug(f"[WebRTC] 피어 {peer_id[:8]} 프레임 {frame_count}개 수신")

        except asyncio.CancelledError:
            logger.info(f"[WebRTC] 피어 {peer_id[:8]} 오디오 컨슈머 태스크 취소됨")
        except Exception as e:
            logger.error(f"[WebRTC] 피어 {peer_id[:8]} 오디오 트랙 컨슈머 오류: {type(e).__name__}: {e}", exc_info=True)
        finally:
            logger.info(f"[WebRTC] 피어 {peer_id[:8]} 오디오 트랙 컨슈머 종료. 총 프레임: {frame_count}")

    async def _start_stt_processing(self, peer_id: str, room_name: str):
        """피어의 오디오 스트림에 대한 STT 처리를 시작합니다.

        오디오 프레임 큐를 생성하고 STT 처리 태스크를 시작합니다.
        각 피어는 독립적인 STTService 인스턴스를 가집니다.

        Args:
            peer_id (str): STT를 시작할 피어의 ID
            room_name (str): 피어가 속한 룸 이름

        Note:
            - 피어당 하나의 STT 처리 태스크만 실행됨
            - 각 피어는 독립적인 Google STT API 스트림을 가짐
            - 인식된 텍스트는 on_transcript_callback으로 전달됨
        """
        if peer_id in self.stt_tasks:
            logger.warning(f"[WebRTC] 피어 {peer_id[:8]} STT 이미 실행 중")
            return

        # Create dedicated STTService instance for this peer
        stt_service = STTService()
        self.stt_services[peer_id] = stt_service

        # Create audio queue for this peer
        # Increased from 100 to 500 to prevent overflow during STT restarts
        # 48kHz audio = ~50 frames/sec, so 500 frames = ~10 seconds buffer
        audio_queue = asyncio.Queue(maxsize=500)
        self.audio_queues[peer_id] = audio_queue

        # Ring buffer to allow gapless restart (keep ~1.5s of latest frames)
        ring_buffer_size = 75  # ~50fps * 1.5s
        self.audio_ring_buffers[peer_id] = deque(maxlen=ring_buffer_size)

        # Start STT processing task
        task = asyncio.create_task(
            self._process_stt_for_peer(peer_id, room_name, audio_queue, stt_service)
        )
        self.stt_tasks[peer_id] = task

        logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 처리 시작 (룸: {room_name})")

    async def _prefill_queue_from_ring_buffer(
        self,
        peer_id: str,
        audio_queue: asyncio.Queue,
        reason: str = "",
        force: bool = False
    ):
        """최근 프레임 링버퍼를 큐에 재주입하여 재시작 공백을 줄입니다.

        Args:
            peer_id: 피어 ID
            audio_queue: 오디오 프레임 큐
            reason: 재주입 사유 (로깅용)
            force: True면 큐 상태와 관계없이 재주입 (타임아웃 복구용)

        Note:
            - 큐에 이미 충분한 프레임이 있으면 중복 방지를 위해 스킵
            - 타임아웃/에러 복구 시에만 force=True로 호출
        """
        ring_buffer = self.audio_ring_buffers.get(peer_id)
        if not ring_buffer:
            return

        # 큐에 이미 충분한 프레임이 있으면 재주입 스킵 (중복 방지)
        # force=True인 경우 (타임아웃 복구) 이 체크 건너뜀
        min_queue_threshold = 25  # ~50fps * 0.5s
        current_queue_size = audio_queue.qsize()
        if not force and current_queue_size >= min_queue_threshold:
            logger.debug(
                f"[WebRTC] 링버퍼 재주입 스킵 (peer={peer_id[:8]}, queue={current_queue_size}, reason={reason})"
            )
            return

        trimmed = 0
        # Drop stale backlog so the latest audio fits
        while audio_queue.qsize() > len(ring_buffer):
            try:
                audio_queue.get_nowait()
                trimmed += 1
            except asyncio.QueueEmpty:
                break

        enqueued = 0
        # Copy to avoid mutation while iterating
        for frame in list(ring_buffer):
            try:
                audio_queue.put_nowait(frame)
                enqueued += 1
            except asyncio.QueueFull:
                break

        if trimmed or enqueued:
            logger.info(
                f"[WebRTC] 링버퍼 재주입 (peer={peer_id[:8]}, enqueued={enqueued}, trimmed={trimmed}, reason={reason})"
            )

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
                # Re-inject the latest audio before opening a new stream
                await self._prefill_queue_from_ring_buffer(peer_id, audio_queue, reason="restart")
                logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 스트림 #{retry_count + 1} 시작")

                async for result in stt_service.process_audio_stream(audio_queue):
                    transcript = result.get("transcript", "")
                    is_final = result.get("is_final", True)
                    confidence = result.get("confidence", 0.0)

                    # 신뢰도 필터링: 낮은 신뢰도 결과는 무시 (배경 잡음 필터링)
                    min_confidence = 0.7
                    if confidence < min_confidence:
                        logger.debug(f"[WebRTC] 피어 {peer_id[:8]} STT 무시 (신뢰도 {confidence:.2f} < {min_confidence}): {transcript}")
                        continue

                    logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 최종: {transcript} (신뢰도: {confidence:.2f})")

                    # Call callback if set (with source identifier and is_final flag)
                    if self.on_transcript_callback and transcript.strip():
                        await self.on_transcript_callback(peer_id, room_name, transcript, connection_config.STT_ENGINE, is_final)

                # Stream ended normally - restart it for continuous recognition
                logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 스트림 정상 종료, 연속 인식을 위해 재시작...")

                # 큐에 남은 프레임 유지 (버퍼링) - 새 스트림에서 처리
                # 정상 종료 시에는 ring buffer 재주입 불필요 (이미 처리된 오디오)
                queue_size = audio_queue.qsize()
                if queue_size > 0:
                    logger.info(f"[WebRTC] 버퍼 프레임 {queue_size}개 유지 (새 스트림용)")

                # 빠르게 재시작 (지연 최소화)
                await asyncio.sleep(0.05)

                # Create new STT service for fresh stream
                stt_service = STTService()
                self.stt_services[peer_id] = stt_service
                continue  # Restart the loop instead of breaking

            except asyncio.CancelledError:
                logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 처리 취소됨")
                raise

            except Exception as e:
                retry_count += 1
                error_msg = str(e)

                # Check if it's a timeout error
                if "timeout" in error_msg.lower() or "409" in error_msg:
                    logger.warning(
                        f"[WebRTC] 피어 {peer_id[:8]} STT 스트림 타임아웃 "
                        f"(시도 {retry_count}/{max_retries}), 스트림 재시작..."
                    )

                    # Trim backlog but keep the most recent frames so restart is gapless
                    queue_size = audio_queue.qsize()
                    if queue_size > 0:
                        keep_after_trim = len(self.audio_ring_buffers.get(peer_id) or [])
                        trimmed = 0
                        while audio_queue.qsize() > keep_after_trim:
                            try:
                                audio_queue.get_nowait()
                                trimmed += 1
                            except asyncio.QueueEmpty:
                                break
                        logger.info(f"[WebRTC] 오디오 큐 트림: {trimmed}개 제거, 남은 {audio_queue.qsize()}개")

                    # Re-inject latest frames from ring buffer to cover the timeout gap
                    # force=True: 타임아웃으로 인한 공백 복구 필요
                    await self._prefill_queue_from_ring_buffer(peer_id, audio_queue, reason="timeout", force=True)

                    # Wait a bit before retrying
                    await asyncio.sleep(0.5)

                    # Create new STT service instance to reset stream
                    stt_service = STTService()
                    self.stt_services[peer_id] = stt_service
                    continue
                else:
                    # Other errors - log and retry
                    logger.error(
                        f"[WebRTC] 피어 {peer_id[:8]} STT 처리 오류: {e}",
                        exc_info=True
                    )
                    await asyncio.sleep(1)
                    continue

        if retry_count >= max_retries:
            logger.error(f"[WebRTC] 피어 {peer_id[:8]} STT 최대 재시도 횟수 도달")

    async def _stop_stt_processing(self, peer_id: str):
        """피어의 STT 처리를 중지합니다.

        STT 처리 태스크를 취소하고 오디오 큐 및 STT 서비스를 정리합니다.

        Args:
            peer_id (str): STT를 중지할 피어의 ID
        """
        # Cancel STT task
        if peer_id in self.stt_tasks:
            task = self.stt_tasks[peer_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.stt_tasks[peer_id]

        # Clear audio queue
        if peer_id in self.audio_queues:
            # Send None to signal end of stream
            try:
                await self.audio_queues[peer_id].put(None)
            except asyncio.QueueFull:
                pass
            del self.audio_queues[peer_id]

        # Remove ring buffer
        if peer_id in self.audio_ring_buffers:
            del self.audio_ring_buffers[peer_id]

        # Remove STT service instance
        if peer_id in self.stt_services:
            del self.stt_services[peer_id]

        logger.info(f"[WebRTC] 피어 {peer_id[:8]} STT 처리 중지")
