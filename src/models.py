from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AnalysisRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    image_path: str | None = None
    ingredients: Any = None
    totals: Any = None
    status: str = "pending"