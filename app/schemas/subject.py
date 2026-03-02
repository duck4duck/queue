from pydantic import BaseModel, ConfigDict
from typing import List


class Subject(BaseModel):
    name: str

    model_config = ConfigDict(from_attributes=True)


class SubjectResponse(Subject):
    id: int


class ListOfSubjects(BaseModel):
    subject_list: List[SubjectResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)
