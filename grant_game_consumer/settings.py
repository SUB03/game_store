from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # "broker:29092" is the Kafka INTERNAL listener for in-network clients;
    # the broker's advertised EXTERNAL listener (port 9092) resolves to
    # "localhost", which is unreachable from other containers.
    kafka_bootstrap_servers: str = "broker:29092"
    grant_requests_topic: str = "payment.grant-requests"
    grant_results_topic: str = "payment.grant-results"
    dead_letter_topic: str = "payment.dead-letters"
    users_service_addr: str = "users_service:8003"
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
