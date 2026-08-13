from pydantic import BaseModel
from pydantic.config import ConfigDict


class F1BaseModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
    )
