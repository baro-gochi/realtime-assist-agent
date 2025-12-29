"""인증 API 라우터.

비밀번호 검증 등 인증 관련 엔드포인트들을 제공합니다.
"""

from fastapi import APIRouter, HTTPException, Form

from .deps import ACCESS_PASSWORD

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/verify")
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
