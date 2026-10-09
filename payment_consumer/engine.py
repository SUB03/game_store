from pydantic import Field
from pydantic_settings import BaseSettings

from sqlalchemy.ext.asyncio import create_async_engine


class EngineSettings(BaseSettings):
    db_url: str = Field(alias="SQLALCHEMY_URL")


engine_settings = EngineSettings()

engine = create_async_engine(engine_settings.db_url)
