"""FastAPI 라우터 모듈.

app.py에서 분리된 API 엔드포인트들을 제공합니다.
"""

from .health import router as health_router
from .consultation import router as consultation_router
from .agent_api import router as agent_router
from .logs import router as logs_router
from .auth import router as auth_router
from .signaling import router as signaling_router, init_managers as init_signaling_managers
from .deps import verify_auth_header, verify_ws_token

__all__ = [
    "health_router",
    "consultation_router",
    "agent_router",
    "logs_router",
    "auth_router",
    "signaling_router",
    "init_signaling_managers",
    "verify_auth_header",
    "verify_ws_token",
]
