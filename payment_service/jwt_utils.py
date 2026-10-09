from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from fastapi import HTTPException, status
import jwt

class Settings(BaseSettings):
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(alias="JWT_ALGORITHM")
    model_config = SettingsConfigDict(extra='ignore', env_file=".env")

settings = Settings()

def decode_jwt(token: str):
    credentials_exeption = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.InvalidTokenError:
        raise credentials_exeption
    except jwt.ExpiredSignatureError:
        raise credentials_exeption
    return payload
