from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import qualification
from app.agents.base import AgentContext
from app.api.deps import current_user
from app.core.db import get_session
from app.core.llm import get_llm
from app.core.security import create_token, hash_password, verify_password
from app.models import Lead, Message, Role, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    role: Role
    lead_id: int | None


class Session(BaseModel):
    token: str
    user: UserOut


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _session(user: User) -> Session:
    return Session(token=create_token(user.id, user.role), user=UserOut.model_validate(user))


async def _by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(func.lower(User.email) == email.lower()))


@router.post("/register")
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)) -> Session:
    """Alta pública: solo crea clientes. Cada cliente tiene su propia conversación comercial."""
    if await _by_email(session, data.email):
        raise HTTPException(409, "an account with that email already exists")
    lead = Lead(name=data.name, email=data.email)
    session.add(lead)
    await session.flush()
    greeting = await qualification.first_question(AgentContext(session=session, llm=get_llm(), lead=lead))
    session.add(Message(lead_id=lead.id, role="assistant", agent="qualification", content=greeting))
    user = User(
        email=data.email.lower(),
        name=data.name,
        password_hash=hash_password(data.password),
        role=Role.client,
        lead_id=lead.id,
    )
    session.add(user)
    await session.commit()
    return _session(user)


@router.post("/login")
async def login(data: LoginIn, session: AsyncSession = Depends(get_session)) -> Session:
    user = await _by_email(session, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "incorrect email or password")
    return _session(user)


@router.get("/me")
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)
