from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    shopid: str
    ukass_api_key: str = Field(alias="UKASS_API_KEY")
    frontend_url: str = Field(alias="FRONTEND_URL")
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
