from enum import StrEnum

from pydantic import BaseModel, Field


class Epic(BaseModel):
    id: str
    title: str
    description: str = ""


class UserStory(BaseModel):
    id: str
    epic_id: str
    as_a: str
    i_want: str
    so_that: str = ""
    acceptance_criteria: list[str] = []
    # Trazabilidad: mensajes del cliente de los que sale la historia
    source_message_ids: list[int] = []


class NFR(BaseModel):
    id: str
    category: str
    text: str
    source_message_ids: list[int] = []


class AmbiguityStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class Ambiguity(BaseModel):
    id: str
    question: str
    status: AmbiguityStatus = AmbiguityStatus.open
    resolution: str | None = None


class RequirementDoc(BaseModel):
    epics: list[Epic] = []
    stories: list[UserStory] = []
    nfrs: list[NFR] = []
    out_of_scope: list[str] = []
    ambiguities: list[Ambiguity] = []
    summary: str | None = Field(default=None, description="Summary proposed to the client for confirmation")

    def open_ambiguities(self) -> list[Ambiguity]:
        return [a for a in self.ambiguities if a.status == AmbiguityStatus.open]

    def readiness_problems(self) -> list[str]:
        """Motivos por los que el documento todavía no se puede confirmar."""
        problems = []
        if not self.stories:
            problems.append("There are no user stories.")
        if self.open_ambiguities():
            n = len(self.open_ambiguities())
            problems.append("There is 1 open ambiguity." if n == 1 else f"There are {n} open ambiguities.")
        epic_ids = {e.id for e in self.epics}
        orphan = [s.id for s in self.stories if s.epic_id not in epic_ids]
        if orphan:
            problems.append(f"Stories without a valid epic: {', '.join(orphan)}.")
        no_ac = [s.id for s in self.stories if not s.acceptance_criteria]
        if no_ac:
            problems.append(f"Stories without acceptance criteria: {', '.join(no_ac)}.")
        if not self.summary:
            problems.append("The summary for the client is missing.")
        return problems
