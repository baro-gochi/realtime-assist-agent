"""FastAPI WebRTC Signaling Server with Room Support.

이 모듈은 WebRTC 기반의 멀티룸 비디오/오디오 상담 시스템을 위한
시그널링 서버를 제공합니다. FastAPI와 WebSocket을 사용하여
실시간 peer-to-peer 연결을 관리합니다.

주요 기능:
    - 룸 기반 피어 관리 (다중 상담 세션 지원)
    - WebRTC offer/answer 교환
    - ICE candidate 처리
    - 실시간 참가자 입/퇴장 알림
    - CORS 설정을 통한 크로스 오리진 요청 지원

Architecture:
    - SFU (Selective Forwarding Unit) 패턴 사용
    - PeerConnectionManager: WebRTC 연결 관리
    - RoomManager: 룸 및 참가자 상태 관리
    - WebSocket: 실시간 시그널링 메시지 전송

Examples:
    서버 실행:
        $ python app.py
        또는
        $ uvicorn app:app --host 0.0.0.0 --port 8000

    클라이언트 연결:
        ws://localhost:8000/ws

API Endpoints:
    GET /: 서버 상태 확인
    GET /rooms: 활성 룸 목록 조회
    WebSocket /ws: 시그널링 메시지 교환

WebSocket Message Types:
    Client -> Server:
        - join_room: 룸 참가 요청
        - offer: WebRTC offer 전송
        - ice_candidate: ICE candidate 전송
        - leave_room: 룸 퇴장 요청
        - get_rooms: 룸 목록 요청

    Server -> Client:
        - peer_id: 클라이언트 고유 ID 할당
        - room_joined: 룸 참가 성공
        - user_joined: 새 참가자 입장 알림
        - user_left: 참가자 퇴장 알림
        - answer: WebRTC answer 응답
        - rooms_list: 룸 목록 응답
        - error: 에러 메시지

See Also:
    room_manager.py: 룸 상태 관리
    peer_manager.py: WebRTC 연결 관리
"""
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict

from peer_manager import PeerConnectionManager
from room_manager import RoomManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global managers
peer_manager = PeerConnectionManager()
room_manager = RoomManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 앱의 생명주기를 관리하는 컨텍스트 매니저.

    서버 시작 시 초기화 작업을 수행하고, 종료 시 정리 작업을 수행합니다.
    모든 활성 WebRTC 연결을 안전하게 종료하여 리소스 누수를 방지합니다.

    Args:
        app (FastAPI): FastAPI 애플리케이션 인스턴스

    Yields:
        None: 앱이 실행되는 동안 제어를 반환

    Note:
        - 시작: 로깅 초기화 및 서버 시작 로그 기록
        - 종료: 모든 피어 연결 정리 및 리소스 해제
    """
    # Startup
    logger.info("Starting up WebRTC Signaling Server...")
    yield
    # Shutdown
    logger.info("Shutting down server...")
    await peer_manager.cleanup_all()


app = FastAPI(title="WebRTC Signaling Server with Rooms", lifespan=lifespan)

origins = [
    "http://localhost:3000",
    "https://my-dev-webrtc.loca.lt",
    "http://172.30.1.56:3000",
]

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignalingMessage(BaseModel):
    """WebSocket 시그널링 메시지 데이터 구조.

    WebRTC 시그널링을 위한 표준 메시지 형식을 정의합니다.
    클라이언트와 서버 간 통신에 사용되는 모든 메시지가 이 형식을 따릅니다.

    Attributes:
        type (str): 메시지 타입 (예: 'join_room', 'offer', 'answer', 'ice_candidate')
        data (dict): 메시지 타입에 따른 추가 데이터. 기본값은 빈 딕셔너리

    Examples:
        룸 참가 메시지:
            >>> msg = SignalingMessage(
            ...     type="join_room",
            ...     data={"room_name": "room1", "nickname": "User1"}
            ... )

        WebRTC offer 메시지:
            >>> msg = SignalingMessage(
            ...     type="offer",
            ...     data={"sdp": "...", "type": "offer"}
            ... )
    """
    type: str
    data: dict = {}


@app.get("/")
async def root():
    """서버 상태 확인 엔드포인트 (Health check).

    서버가 정상적으로 실행 중인지 확인하는 간단한 헬스체크 엔드포인트입니다.
    모니터링 및 로드 밸런서에서 서버 상태를 확인하는 데 사용됩니다.

    Returns:
        dict: 서버 상태 정보를 포함하는 딕셔너리
            - status (str): 서버 상태 ("ok" 또는 오류 상태)
            - service (str): 서비스 이름

    Examples:
        >>> response = await root()
        >>> print(response)
        {"status": "ok", "service": "WebRTC Signaling Server with Rooms"}
    """
    return {"status": "ok", "service": "WebRTC Signaling Server with Rooms"}


@app.get("/rooms")
async def get_rooms():
    """활성화된 모든 룸의 목록을 조회합니다.

    현재 서버에 생성되어 있는 모든 룸과 각 룸의 참가자 정보를 반환합니다.
    클라이언트가 참가 가능한 룸을 확인하거나, 관리자가 시스템 상태를
    모니터링하는 데 사용됩니다.

    Returns:
        dict: 룸 목록을 포함하는 딕셔너리
            - rooms (List[dict]): 각 룸의 정보 리스트
                - room_name (str): 룸 이름
                - peer_count (int): 현재 참가자 수
                - peers (List[dict]): 참가자 정보 리스트
                    - peer_id (str): 참가자 고유 ID
                    - nickname (str): 참가자 닉네임

    Examples:
        >>> response = await get_rooms()
        >>> print(response)
        {
            "rooms": [
                {
                    "room_name": "상담실1",
                    "peer_count": 2,
                    "peers": [
                        {"peer_id": "abc-123", "nickname": "상담사"},
                        {"peer_id": "def-456", "nickname": "내담자"}
                    ]
                }
            ]
        }
    """
    return {"rooms": room_manager.get_room_list()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebRTC 시그널링을 위한 WebSocket 엔드포인트.

    클라이언트와의 WebSocket 연결을 통해 실시간 시그널링 메시지를 주고받습니다.
    룸 참가/퇴장, WebRTC offer/answer 교환, ICE candidate 처리 등을 담당합니다.

    처리하는 메시지 타입:
        - join_room: 특정 룸에 참가 (room_name, nickname 필요)
        - offer: WebRTC offer 전송 (sdp, type 포함)
        - ice_candidate: ICE candidate 정보 전송
        - leave_room: 현재 룸에서 퇴장
        - get_rooms: 활성 룸 목록 요청

    Args:
        websocket (WebSocket): FastAPI WebSocket 연결 객체

    Workflow:
        1. 연결 수락 및 고유 peer_id 생성
        2. peer_id를 클라이언트에 전송
        3. 메시지 수신 및 타입별 처리:
            - join_room: 룸 참가 처리 및 다른 참가자에게 알림
            - offer: WebRTC offer 처리 및 answer 생성/전송
            - ice_candidate: ICE candidate 처리
            - leave_room: 룸 퇴장 및 정리
        4. 연결 종료 시 자동 정리 (룸 퇴장, peer 연결 종료)

    Raises:
        WebSocketDisconnect: 클라이언트 연결이 끊어진 경우
        Exception: 메시지 처리 중 발생한 오류

    Note:
        - 각 클라이언트는 한 번에 하나의 룸에만 참가 가능
        - 연결 종료 시 자동으로 정리 작업 수행 (finally 블록)
        - 모든 에러는 로그로 기록되며, 적절한 에러 메시지를 클라이언트에 전송

    Examples:
        클라이언트 연결 예시 (JavaScript):
            >>> const ws = new WebSocket('ws://localhost:8000/ws');
            >>> ws.onmessage = (event) => {
            ...     const msg = JSON.parse(event.data);
            ...     if (msg.type === 'peer_id') {
            ...         console.log('My peer ID:', msg.data.peer_id);
            ...     }
            ... };

        룸 참가 메시지 전송:
            >>> ws.send(JSON.stringify({
            ...     type: 'join_room',
            ...     data: {
            ...         room_name: '상담실1',
            ...         nickname: '상담사'
            ...     }
            ... }));
    """
    await websocket.accept()

    peer_id = str(uuid.uuid4())
    current_room = None
    nickname = None

    logger.info(f"Peer {peer_id} connected")

    # Send peer ID to client
    await websocket.send_json({
        "type": "peer_id",
        "data": {"peer_id": peer_id}
    })

    # Register callback for track received event
    async def on_track_received(source_peer_id: str, room_name: str, track_kind: str):
        """트랙 수신 시 호출되는 콜백 함수.

        새로운 미디어 트랙이 수신되었을 때 같은 룸의 다른 피어들에게
        renegotiation이 필요하다는 알림을 브로드캐스트합니다.

        Args:
            source_peer_id (str): 트랙을 전송한 피어의 ID
            room_name (str): 트랙이 수신된 룸 이름
            track_kind (str): 트랙 종류 ("audio" 또는 "video")

        Note:
            - 트랙 전송자는 알림 대상에서 제외됨
            - PeerConnectionManager에서 on_track 이벤트 시 자동 호출됨
        """
        logger.info(f"📡 Track received from {source_peer_id}: {track_kind}")
        # 같은 방의 다른 피어들에게 renegotiation 요청
        await broadcast_to_room(
            room_name,
            {
                "type": "renegotiation_needed",
                "data": {
                    "reason": "track_received",
                    "source_peer_id": source_peer_id,
                    "track_kind": track_kind
                }
            },
            exclude=[source_peer_id]
        )

    peer_manager.on_track_received_callback = on_track_received

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "join_room":
                # Handle room join
                room_name = data.get("data", {}).get("room_name")
                nickname = data.get("data", {}).get("nickname", "Anonymous")

                if not room_name:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Room name is required"}
                    })
                    continue

                # Join room
                room_manager.join_room(room_name, peer_id, nickname, websocket)
                current_room = room_name

                # Get other peers in room
                other_peers = room_manager.get_other_peers(room_name, peer_id)

                # Send room joined confirmation
                await websocket.send_json({
                    "type": "room_joined",
                    "data": {
                        "room_name": room_name,
                        "peer_count": room_manager.get_room_count(room_name),
                        "other_peers": [
                            {"peer_id": p.peer_id, "nickname": p.nickname}
                            for p in other_peers
                        ]
                    }
                })

                # Notify other peers in room
                await broadcast_to_room(
                    room_name,
                    {
                        "type": "user_joined",
                        "data": {
                            "peer_id": peer_id,
                            "nickname": nickname,
                            "peer_count": room_manager.get_room_count(room_name)
                        }
                    },
                    exclude=[peer_id]
                )

                # Renegotiation will be triggered when tracks are actually received
                # on_track_received 콜백에서 트랙 수신 시 자동으로 renegotiation 요청됨
                logger.info(f"Peer {peer_id} joined - will trigger renegotiation when tracks arrive")

                logger.info(f"Peer {nickname} ({peer_id}) joined room '{room_name}'")

            elif message_type == "offer":
                # Handle WebRTC offer
                if not current_room:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Not in a room"}
                    })
                    continue

                offer = data.get("data")
                logger.info(f"Received offer from {peer_id} in room '{current_room}'")

                try:
                    # Get other peers in room
                    other_peers = room_manager.get_other_peers(current_room, peer_id)
                    other_peer_ids = [p.peer_id for p in other_peers]

                    # Handle offer and create answer
                    answer = await peer_manager.handle_offer(
                        peer_id,
                        current_room,
                        offer,
                        other_peer_ids
                    )

                    # Send answer back to peer
                    await websocket.send_json({
                        "type": "answer",
                        "data": answer
                    })

                    logger.info(f"Sent answer to {peer_id}")
                except Exception as e:
                    logger.error(f"Error handling offer from {peer_id}: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": str(e)}
                    })

            elif message_type == "ice_candidate":
                # Handle ICE candidate
                if not current_room:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Not in a room"}
                    })
                    continue

                candidate_data = data.get("data")
                logger.info(f"Received ICE candidate from {peer_id}")

                # Broadcast ICE candidate to other peers in the room
                await broadcast_to_room(
                    current_room,
                    {
                        "type": "ice_candidate",
                        "data": candidate_data
                    },
                    exclude=[peer_id]
                )

            elif message_type == "leave_room":
                # Handle room leave
                if current_room:
                    # Notify others
                    await broadcast_to_room(
                        current_room,
                        {
                            "type": "user_left",
                            "data": {
                                "peer_id": peer_id,
                                "nickname": nickname,
                                "peer_count": room_manager.get_room_count(current_room) - 1
                            }
                        },
                        exclude=[peer_id]
                    )

                    # Leave room
                    room_manager.leave_room(peer_id)
                    await peer_manager.close_peer_connection(peer_id)

                    logger.info(f"Peer {nickname} ({peer_id}) left room '{current_room}'")
                    current_room = None

            elif message_type == "get_rooms":
                # Send list of available rooms
                await websocket.send_json({
                    "type": "rooms_list",
                    "data": {"rooms": room_manager.get_room_list()}
                })

            else:
                logger.warning(f"Unknown message type from {peer_id}: {message_type}")

    except WebSocketDisconnect:
        logger.info(f"Peer {peer_id} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket connection for {peer_id}: {e}")
    finally:
        # Cleanup
        if current_room:
            # Notify others in room
            await broadcast_to_room(
                current_room,
                {
                    "type": "user_left",
                    "data": {
                        "peer_id": peer_id,
                        "nickname": nickname,
                        "peer_count": room_manager.get_room_count(current_room) - 1
                    }
                },
                exclude=[peer_id]
            )

            room_manager.leave_room(peer_id)

        await peer_manager.close_peer_connection(peer_id)
        logger.info(f"Peer {peer_id} cleaned up")


async def broadcast_to_room(room_name: str, message: dict, exclude: list = None):
    """특정 룸의 모든 참가자에게 메시지를 브로드캐스트합니다.

    지정된 룸의 모든 피어에게 메시지를 전송하며, 선택적으로 특정 피어를
    제외할 수 있습니다. 메시지 전송 실패 시 해당 피어를 자동으로 정리합니다.

    Args:
        room_name (str): 메시지를 전송할 룸 이름
        message (dict): 전송할 메시지 딕셔너리 (JSON 직렬화 가능해야 함)
        exclude (list, optional): 메시지를 받지 않을 peer_id 리스트. 기본값은 None

    Note:
        - 메시지 전송 실패 시 해당 피어는 자동으로 정리됨
        - 연결이 끊어진 피어는 disconnected 리스트에 추가되어 일괄 정리
        - 전송 실패는 WARNING 레벨로 로깅됨

    Examples:
        새 참가자 입장 알림:
            >>> await broadcast_to_room(
            ...     "상담실1",
            ...     {
            ...         "type": "user_joined",
            ...         "data": {
            ...             "peer_id": "new-peer-123",
            ...             "nickname": "새 참가자",
            ...             "peer_count": 3
            ...         }
            ...     },
            ...     exclude=["new-peer-123"]  # 본인 제외
            ... )

        참가자 퇴장 알림:
            >>> await broadcast_to_room(
            ...     "상담실1",
            ...     {
            ...         "type": "user_left",
            ...         "data": {
            ...             "peer_id": "leaving-peer-456",
            ...             "nickname": "퇴장자",
            ...             "peer_count": 2
            ...         }
            ...     },
            ...     exclude=["leaving-peer-456"]
            ... )
    """
    exclude = exclude or []
    peers = room_manager.get_room_peers(room_name)
    disconnected = []

    for peer in peers:
        if peer.peer_id not in exclude:
            try:
                await peer.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {peer.peer_id}: {e}")
                disconnected.append(peer.peer_id)

    # Cleanup disconnected peers
    for peer_id in disconnected:
        room_manager.leave_room(peer_id)
        await peer_manager.close_peer_connection(peer_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
