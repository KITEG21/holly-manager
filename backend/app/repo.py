"""Lectura/escritura de la configuración del panel, siempre a través de los modelos Pydantic."""

from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, QualificationCriterion, TaskType
from app.schemas.config import CommercialRules, QualificationThresholds, TaskTypeConfig, TeamConfig
from app.schemas.qualification import QualificationCriterionConfig

T = TypeVar("T", bound=BaseModel)

SETTING_MODELS: dict[str, type[BaseModel]] = {
    "team": TeamConfig,
    "commercial": CommercialRules,
    "qualification": QualificationThresholds,
}


async def get_setting(session: AsyncSession, key: str, model: type[T]) -> T:
    row = await session.get(AppSetting, key)
    return model.model_validate(row.value) if row else model()


async def put_setting(session: AsyncSession, key: str, value: BaseModel) -> None:
    data = value.model_dump(mode="json")
    stmt = insert(AppSetting).values(key=key, value=data)
    await session.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={"value": data}))


async def get_team(session: AsyncSession) -> TeamConfig:
    return await get_setting(session, "team", TeamConfig)


async def get_rules(session: AsyncSession) -> CommercialRules:
    return await get_setting(session, "commercial", CommercialRules)


async def get_thresholds(session: AsyncSession) -> QualificationThresholds:
    return await get_setting(session, "qualification", QualificationThresholds)


async def get_task_types(session: AsyncSession) -> dict[str, TaskTypeConfig]:
    rows = (await session.scalars(select(TaskType).order_by(TaskType.name))).all()
    return {r.name: TaskTypeConfig.model_validate(r) for r in rows}


async def get_criteria(session: AsyncSession) -> list[QualificationCriterionConfig]:
    rows = (await session.scalars(select(QualificationCriterion).order_by(QualificationCriterion.id))).all()
    return [QualificationCriterionConfig.model_validate(r) for r in rows]
