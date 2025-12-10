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
import asyncio
from contextlib import asynccontextmanager
import os
from collections import defaultdict
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Depends, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import httpx

from modules import PeerConnectionManager, RoomManager, get_db_manager, get_redis_manager, DatabaseLogHandler
from modules import consultation_router, comparison_router, faq_router
from modules.agent import get_or_create_agent, remove_agent, room_agents
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from config/.env
load_dotenv(Path(__file__).parent / "config" / ".env")

# Access password for authentication
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "")


async def verify_auth_header(authorization: Optional[str] = Header(None)) -> bool:
    """Authorization 헤더를 검증합니다."""
    if not ACCESS_PASSWORD:
        return True
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    if parts[1] != ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return True


def verify_ws_token(token: Optional[str]) -> bool:
    """WebSocket 연결 시 토큰을 검증합니다."""
    if not ACCESS_PASSWORD:
        return True
    return token == ACCESS_PASSWORD


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global managers
peer_manager = PeerConnectionManager()
room_manager = RoomManager()

# Database and Redis managers (will be initialized in lifespan)
db_manager = get_db_manager()
redis_manager = get_redis_manager()
db_log_handler: Optional[DatabaseLogHandler] = None
summary_counters: defaultdict[str, int] = defaultdict(int)


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
        - 시작: DB 초기화, 로그 핸들러 시작, 서버 시작
        - 종료: 로그 핸들러 정지, DB 연결 종료, 피어 연결 정리
    """
    global db_log_handler

    # Startup
    logger.info("Starting up WebRTC Signaling Server...")

    # Initialize database connection
    db_initialized = await db_manager.initialize()
    if db_initialized:
        logger.info("Database connection established")

        # Start database log handler
        db_log_handler = DatabaseLogHandler(level=logging.INFO)
        logging.getLogger().addHandler(db_log_handler)
        await db_log_handler.start()
        logger.info("Database log handler started")
    else:
        logger.warning("Database not available, running without DB logging")

    # Initialize Redis connection
    redis_initialized = await redis_manager.initialize()
    if redis_initialized:
        logger.info("Redis connection established")
    else:
        logger.warning("Redis not available, running without Redis")

    yield

    # Shutdown
    logger.info("Shutting down server...")

    # Stop database log handler
    if db_log_handler:
        await db_log_handler.stop()
        logger.info("Database log handler stopped")

    # Close Redis connection
    if redis_manager.is_initialized:
        await redis_manager.close()
        logger.info("Redis connection closed")

    # Close database connection
    if db_manager.is_initialized:
        await db_manager.close()
        logger.info("Database connection closed")

    # Cleanup peer connections
    await peer_manager.cleanup_all()


app = FastAPI(title="WebRTC Signaling Server with Rooms", lifespan=lifespan)

# CORS - 개발 환경에서는 모든 로컬 네트워크 허용
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|172\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+$|^https://.*\.loca\.lt$|^https://baro-gochi\.github\.io$|^https://.*\.ngrok(-free)?\.(app|dev|io)$|^https://.*\.trycloudflare\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include consultation module routers (RAG-based consultation support)
app.include_router(consultation_router, prefix="/api")
app.include_router(comparison_router, prefix="/api")
app.include_router(faq_router, prefix="/api")


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


@app.post("/api/auth/verify")
async def verify_password(password: str = Form("")):
    """비밀번호를 검증합니다.

    프론트엔드에서 비밀번호 입력 후 검증 요청에 사용됩니다.

    Args:
        password: 검증할 비밀번호

    Returns:
        dict: 인증 결과 {"success": bool, "message": str}
    """
    if not ACCESS_PASSWORD:
        return {"success": True, "message": "No password required"}
    if password == ACCESS_PASSWORD:
        return {"success": True, "message": "Authenticated"}
    raise HTTPException(status_code=401, detail="Invalid password")


@app.get("/api/rooms")
async def get_rooms_api(_: bool = Depends(verify_auth_header)):
    """활성화된 모든 룸의 목록을 조회합니다 (API 엔드포인트).

    /rooms와 동일한 기능을 제공하며, Vite 프록시 설정과 호환됩니다.
    프론트엔드에서 /api 경로를 통해 접근할 수 있습니다.

    Returns:
        dict: 룸 목록을 포함하는 딕셔너리 (/rooms와 동일한 형식)
    """
    return {"rooms": room_manager.get_room_list()}


@app.get("/api/turn-credentials")
async def get_turn_credentials(_: bool = Depends(verify_auth_header)):
    """TURN 서버 credentials를 Frontend에 안전하게 제공합니다.

    AWS coturn 서버의 고정 credentials를 클라이언트에 전달합니다.
    이 엔드포인트는 Backend에서 credentials를 관리하여 Frontend에서 민감한 정보가
    노출되지 않도록 합니다.

    Returns:
        list: TURN 서버 ICE server 설정 리스트 또는 에러 메시지
            - 성공 시: ICE servers 배열 (STUN + TURN)
            - 실패 시: {"error": "에러 메시지"}

    Environment Variables:
        TURN_SERVER_URL: AWS coturn TURN 서버 URL
        TURN_USERNAME: AWS coturn 사용자명
        TURN_CREDENTIAL: AWS coturn 비밀번호
        STUN_SERVER_URL: AWS coturn STUN 서버 URL (선택)

    Security:
        - Credentials는 Backend 환경 변수에서만 관리
        - Frontend에 민감한 정보 직접 노출 방지

    Examples:
        성공 응답:
            [
                {
                    "urls": "stun:13.209.180.128:3478"
                },
                {
                    "urls": "turn:13.209.180.128:3478",
                    "username": "username1",
                    "credential": "password1"
                }
            ]

        에러 응답:
            {"error": "TURN service not configured"}
    """
    import os

    turn_server_url = os.getenv("TURN_SERVER_URL")
    turn_username = os.getenv("TURN_USERNAME")
    turn_credential = os.getenv("TURN_CREDENTIAL")
    stun_server_url = os.getenv("STUN_SERVER_URL")

    if not turn_server_url or not turn_username or not turn_credential:
        logger.warning("AWS coturn credentials not set in environment")
        return {"error": "TURN service not configured"}

    ice_servers = []

    # STUN 서버 추가 (AWS coturn)
    if stun_server_url:
        ice_servers.append({"urls": stun_server_url})

    # TURN 서버 추가 (AWS coturn)
    ice_servers.append({
        "urls": turn_server_url,
        "username": turn_username,
        "credential": turn_credential
    })

    logger.info("AWS coturn credentials provided to frontend")
    return ice_servers


# RAG 서버 URL (환경변수로 설정 가능)
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8001")


class RAGAssistRequest(BaseModel):
    """RAG 어시스턴트 요청 모델."""
    summary: str
    include_documents: bool = True
    max_documents: int = 5


@app.post("/api/rag/assist")
async def rag_assist_proxy(
    request: RAGAssistRequest,
    _: bool = Depends(verify_auth_header)
):
    """RAG 서버로 요청을 프록시합니다.

    8001번 포트의 RAG 서버로 요청을 전달하고 응답을 반환합니다.
    이를 통해 프론트엔드는 8000번 포트만 사용하면 됩니다.

    Args:
        request: RAG 어시스턴트 요청
            - summary: 상담 내용 요약
            - include_documents: 관련 문서 포함 여부 (기본값: true)
            - max_documents: 최대 문서 수 (기본값: 5)

    Returns:
        dict: RAG 서버의 응답

    Raises:
        HTTPException: RAG 서버 연결 실패 또는 오류 시
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{RAG_SERVER_URL}/consultation/assist",
                json=request.model_dump(exclude_none=True)
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        logger.error(f"RAG server connection failed: {RAG_SERVER_URL}")
        raise HTTPException(
            status_code=503,
            detail=f"RAG 서버에 연결할 수 없습니다. ({RAG_SERVER_URL})"
        )
    except httpx.TimeoutException:
        logger.error(f"RAG server timeout: {RAG_SERVER_URL}")
        raise HTTPException(
            status_code=504,
            detail="RAG 서버 응답 시간 초과"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"RAG server error: {e.response.status_code}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"RAG 서버 오류: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"RAG proxy error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG 프록시 처리 중 오류: {str(e)}"
        )


@app.get("/api/rag/health")
async def rag_health_check():
    """RAG 서버 상태를 확인합니다.

    Returns:
        dict: RAG 서버 상태 정보
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RAG_SERVER_URL}/health")
            if response.status_code == 200:
                return {
                    "status": "ok",
                    "rag_server": RAG_SERVER_URL,
                    "rag_status": response.json()
                }
            else:
                return {
                    "status": "error",
                    "rag_server": RAG_SERVER_URL,
                    "message": f"RAG 서버 응답 코드: {response.status_code}"
                }
    except Exception as e:
        return {
            "status": "disconnected",
            "rag_server": RAG_SERVER_URL,
            "message": str(e)
        }


@app.get("/api/health/db")
async def db_health_check():
    """PostgreSQL 데이터베이스 상태를 확인합니다.

    Returns:
        dict: DB 연결 상태 정보
    """
    db = get_db_manager()
    if not db.is_initialized:
        return {"status": "error", "message": "Database not initialized"}
    try:
        result = await db.fetchval("SELECT 1")
        return {"status": "ok", "connected": result == 1}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/health/redis")
async def redis_health_check():
    """Redis 상태를 확인합니다.

    Returns:
        dict: Redis 연결 상태 정보
    """
    redis_mgr = get_redis_manager()
    if not redis_mgr.is_initialized:
        return {"status": "error", "message": "Redis not initialized"}
    try:
        pong = await redis_mgr.ping()
        return {"status": "ok", "connected": pong}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/health")
async def health_check():
    """전체 서비스 상태를 확인합니다.

    Returns:
        dict: 모든 서비스 연결 상태 정보
    """
    db = get_db_manager()
    redis_mgr = get_redis_manager()

    db_status = "ok"
    redis_status = "ok"

    # Check DB
    if not db.is_initialized:
        db_status = "not_initialized"
    else:
        try:
            await db.fetchval("SELECT 1")
        except Exception:
            db_status = "error"

    # Check Redis
    if not redis_mgr.is_initialized:
        redis_status = "not_initialized"
    else:
        try:
            if not await redis_mgr.ping():
                redis_status = "error"
        except Exception:
            redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return {
        "status": overall,
        "services": {
            "database": db_status,
            "redis": redis_status,
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
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
    # Verify token before accepting connection
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

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
        logger.info(f"Track received from {source_peer_id}: {track_kind}")
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
    
    # Register callback for ICE candidate
    async def on_ice_candidate(source_peer_id: str, candidate):
          # IMPORTANT: aiortc gives us the candidate object, we need to convert it
          # The candidate string already has "candidate:" prefix, don't add it again

          # DEBUG: Log the raw candidate object
          logger.info(f"Raw candidate from aiortc: candidate={candidate.candidate}, sdpMid={candidate.sdpMid}, sdpMLineIndex={candidate.sdpMLineIndex}")

          candidate_dict = {
              "candidate": candidate.candidate,  # Already has "candidate:" prefix
              "sdpMid": candidate.sdpMid,
              "sdpMLineIndex": candidate.sdpMLineIndex
          }

          logger.info(f"Converted candidate_dict: {candidate_dict}")

          # Broadcast ICE candidate to ALL peers in the same room
          room_name = peer_manager.get_peer_room(source_peer_id)
          if room_name:
              logger.info(f"Broadcasting backend ICE candidate from {source_peer_id} to room '{room_name}'")
              await room_manager.broadcast_to_room(
                  room_name,
                  {
                      "type": "ice_candidate",
                      "data": candidate_dict
                  },
                  exclude=[]  # Send to ALL peers (including source)
              )
          else:
              # Fallback: Send to source peer only if room not found
              logger.warning(f"Room not found for peer {source_peer_id}, sending ICE candidate to source only")
              await websocket.send_json({"type": "ice_candidate", "data": candidate_dict})

    peer_manager.on_ice_candidate_callback = on_ice_candidate

    # Register callback for STT transcript
    async def on_transcript(peer_id: str, room_name: str, transcript: str, source: str = "google", is_final: bool = True):
        """STT 인식 결과를 WebSocket을 통해 전송하고 에이전트를 실행하는 콜백 함수.

        Args:
            peer_id (str): 음성을 전송한 피어의 ID
            room_name (str): 피어가 속한 룸 이름
            transcript (str): 인식된 텍스트
            source (str): STT 엔진 소스
            is_final (bool): 최종 결과 여부

        Note:
            - 같은 룸의 모든 피어에게 브로드캐스트
            - 메시지 형식: {"type": "transcript", "data": {...}}
            - 최종 결과만 LangGraph 에이전트 실행
        """
        logger.info(f"[{source.upper()}] Transcript from {peer_id} in room '{room_name}': {transcript}")

        # Get peer nickname
        peer_info = room_manager.get_peer(peer_id)
        nickname = peer_info.nickname if peer_info else "Unknown"

        # Save transcript to room history (only for Google to avoid duplicates)
        import time
        current_time = time.time()
        if source == "google":
            room_manager.add_transcript(peer_id, room_name, transcript, timestamp=current_time)

        # Broadcast transcript to all peers in room (include source for comparison)
        await broadcast_to_room(
            room_name,
            {
                "type": "transcript",
                "data": {
                    "peer_id": peer_id,
                    "nickname": nickname,
                    "text": transcript,
                    "timestamp": current_time,
                    "source": source,
                    "is_final": is_final  # True for final, False for partial
                }
            }
        )

        # LangGraph 에이전트 실행 (실시간 요약 생성)
        # Skip agent for STT comparison room
        if room_name == "stt-comparison-room":
            logger.debug(f"Skipping agent for STT comparison room")
            return

        # Only run agent for Google STT to avoid duplicate summaries
        if source != "google":
            logger.debug(f"Skipping agent for {source} source (only Google STT triggers agent)")
            return

        try:
            agent = room_agents.get(room_name)

            if not agent:
                logger.warning(f"No agent found for room '{room_name}', skipping summary")
                return

            # 요약 실행 주기: 첫 최종 1회 + 이후 3회마다
            should_run_summary = False
            if is_final:
                summary_counters[room_name] += 1
                count = summary_counters[room_name]
                should_run_summary = (count == 1) or (count % 3 == 0)

            logger.info(
                f"Running agent for room '{room_name}' "
                f"(should_run_summary={should_run_summary}, count={summary_counters.get(room_name, 0)})"
            )
            logger.info(f"Calling agent.on_new_transcript(peer_id={peer_id}, nickname={nickname}, transcript={transcript[:50]}...)")

            # 비스트리밍 모드로 에이전트 실행 (JSON 응답)
            result = await agent.on_new_transcript(
                peer_id,
                nickname,
                transcript,
                current_time,
                run_summary=should_run_summary
            )

            # 에러 체크
            if "error" in result:
                logger.error(f"Agent returned error: {result['error']}")
                return

            # 요약 실행 안 했으면 브로드캐스트 스킵
            if not should_run_summary:
                return

            # 결과 브로드캐스트 (Structured)
            summary_payload = result.get("summary_result", {}) or {}
            current_summary = result.get("current_summary", "")
            last_summarized_index = result.get("last_summarized_index", 0)

            logger.info(f"Broadcasting agent update with structured summary")
            logger.info(f"Summary: {current_summary[:100]}...")

            await broadcast_to_room(
                room_name,
                {
                    "type": "agent_update",
                    "node": "summarize",
                    "data": {
                        "summary": summary_payload.get("summary", ""),
                        "customer_issue": summary_payload.get("customer_issue", ""),
                        "agent_action": summary_payload.get("agent_action", ""),
                        "last_summarized_index": last_summarized_index,
                        "raw": current_summary,
                    }
                }
            )
            logger.info(f"Broadcast completed")

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)

    peer_manager.on_transcript_callback = on_transcript

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

                # 방 생성/입장 시 에이전트 생성 (STT 비교 페이지는 제외)
                if room_name == "stt-comparison-room":
                    logger.info(f"Skipping agent creation for STT comparison room")
                    agent = None
                else:
                    logger.info(f"Creating/getting agent for room '{room_name}'")
                    agent = get_or_create_agent(room_name)
                    logger.info(f"Agent ready for room '{room_name}'")

                # 에이전트 준비 완료 알림 전송 (STT 비교 룸은 제외)
                if agent is not None:
                    await broadcast_to_room(
                        room_name,
                        {
                            "type": "agent_ready",
                            "data": {
                                "llm_available": agent.llm_available
                            }
                        }
                    )

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
                logger.info(f"Received ICE candidate from {peer_id[:8]}")

                # Add ICE candidate to this peer's connection
                pc = peer_manager.get_peer_connection(peer_id)
                if pc and candidate_data:
                    try:
                        from aiortc.sdp import candidate_from_sdp

                        # Unwrap nested structure: {candidate: {candidate: "...", sdpMid: ...}}
                        inner_candidate = candidate_data.get("candidate", {})
                        if isinstance(inner_candidate, dict):
                            candidate_str = inner_candidate.get("candidate", "")
                            sdp_mid = inner_candidate.get("sdpMid")
                            sdp_mline_index = inner_candidate.get("sdpMLineIndex")
                        else:
                            # Fallback: if not nested, use directly
                            candidate_str = candidate_data.get("candidate", "")
                            sdp_mid = candidate_data.get("sdpMid")
                            sdp_mline_index = candidate_data.get("sdpMLineIndex")

                        # Remove "candidate:" prefix if present
                        if candidate_str.startswith("candidate:"):
                            candidate_str = candidate_str[10:]  # len("candidate:")

                        # Parse SDP candidate string to RTCIceCandidate
                        ice_candidate = candidate_from_sdp(candidate_str)
                        ice_candidate.sdpMid = sdp_mid
                        ice_candidate.sdpMLineIndex = sdp_mline_index

                        # Add to peer connection
                        await pc.addIceCandidate(ice_candidate)
                        logger.info(f"  Added client ICE candidate to peer {peer_id[:8]}")
                    except Exception as e:
                        logger.error(f"  Failed to add ICE candidate: {e}")

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

            elif message_type == "agent_task":
                task_payload = data.get("data", {})
                task_type = task_payload.get("task")
                target_room = task_payload.get("room_name") or current_room
                user_options = task_payload.get("user_options")

                if task_type != "consultation":
                    await websocket.send_json({
                        "type": "agent_error",
                        "data": {"task": task_type, "message": "unsupported task"}
                    })
                    continue

                if not target_room:
                    await websocket.send_json({
                        "type": "agent_error",
                        "data": {"task": task_type, "message": "room is required"}
                    })
                    continue

                # 진행 상태 알림
                await websocket.send_json({
                    "type": "agent_status",
                    "data": {"task": "consultation", "status": "processing"}
                })

                try:
                    agent = get_or_create_agent(target_room)
                    result = await agent.run_consultation(user_options=user_options)

                    if "error" in result:
                        await websocket.send_json({
                            "type": "agent_error",
                            "data": {"task": "consultation", "message": result["error"]["message"]}
                        })
                        continue

                    await broadcast_to_room(
                        target_room,
                        {
                            "type": "agent_consultation",
                            "data": result.get("consultation_result", {})
                        }
                    )
                except Exception as e:
                    logger.error(f"Consultation task failed: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "agent_error",
                        "data": {"task": "consultation", "message": str(e)}
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
            if room_manager.get_room_count(current_room) == 0:
                summary_counters.pop(current_room, None)

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
