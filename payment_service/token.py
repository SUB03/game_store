from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

class Token(BaseModel):
    sub: str
    exp: datetime
    jti: UUID
