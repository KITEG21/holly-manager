from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models import Role, User

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    data = decode_token(creds.credentials) if creds else None
    user = await session.get(User, data["sub"]) if data else None
    if user is None:
        raise HTTPException(401, "invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_role(*roles: Role):
    async def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "you do not have permission to access this section")
        return user

    return check


async def lead_access(lead_id: int, user: User = Depends(current_user)) -> User:
    """Un cliente solo puede ver su propia conversación; el admin, todas."""
    if user.role == Role.admin or (user.role == Role.client and user.lead_id == lead_id):
        return user
    raise HTTPException(403, "you do not have access to this project")


AdminOnly = Depends(require_role(Role.admin))
TeamOnly = Depends(require_role(Role.developer, Role.admin))
