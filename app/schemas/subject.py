from pydantic import BaseModel, ConfigDict, Field


class Subject(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(from_attributes=True)


class SubjectResponse(Subject):
    id: int


class ListOfSubjects(BaseModel):
    subject_list: list[SubjectResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)
