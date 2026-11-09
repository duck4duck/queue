from pydantic import BaseModel, ConfigDict


class Subject(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class SubjectResponse(Subject):
    id: int


class ListOfSubjects(BaseModel):
    subject_list: list[SubjectResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)
