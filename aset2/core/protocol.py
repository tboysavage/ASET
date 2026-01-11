from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class StateVariable(BaseModel):
    name: str
    type: str  # e.g., "List[str]"
    description: str


class Fragment(BaseModel):
    id: str  # e.g., "calculate_total"
    description: str
    inputs: List[str]
    outputs: List[str]
    code: Optional[str] = None


class ProjectBlueprint(BaseModel):
    app_name: str
    global_state: List[StateVariable] = Field(default_factory=list)
    logic_fragments: List[Fragment] = Field(default_factory=list)
    ui_layout: str = ""
