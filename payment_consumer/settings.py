from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    shopid: str
    ukass_api_key: str = Field(alias="UKASS_API_KEY")
    # "broker:29092" is the Kafka INTERNAL listener for in-network clients;
    # the broker's advertised EXTERNAL listener (port 9092) resolves to
    # "localhost", which is unreachable from other containers.
    kafka_bootstrap_servers: str = "broker:29092"
    grant_results_topic: str = "payment.grant-results"
    users_service_addr: str = "users_service:8003"
    reconcile_interval_seconds: float = 300
    max_reconcile_attempts: int = 5
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
