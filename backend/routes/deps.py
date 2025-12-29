"""공유 의존성 모듈.

라우터들이 공통으로 사용하는 의존성을 정의합니다.
"""

import os
from typing import Optional

from fastapi import Header, HTTPException

# 접근 비밀번호 설정
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "")


async def verify_auth_header(authorization: Optional[str] = Header(None)) -> bool:
    """Authorization 헤더를 검증합니다.

    Args:
        authorization: Authorization 헤더 값

    Returns:
        bool: 검증 성공 시 True

    Raises:
        HTTPException: 인증 실패 시
    """
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
    """WebSocket 연결 시 토큰을 검증합니다.

    Args:
        token: WebSocket 쿼리 파라미터로 전달된 토큰

    Returns:
        bool: 검증 성공 여부
    """
    if not ACCESS_PASSWORD:
        return True
    return token == ACCESS_PASSWORD
