from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    shopid: str
    ukass_api_key: str = Field(alias="UKASS_API_KEY")
    frontend_url: str = Field(alias="FRONTEND_URL")
    # "broker:29092" is the Kafka INTERNAL listener for in-network clients;
    # the broker's advertised EXTERNAL listener (port 9092) resolves to
    # "localhost", which is unreachable from other containers.
    kafka_bootstrap_servers: str = "broker:29092"
    grant_requests_topic: str = "payment.grant-requests"
    grant_results_topic: str = "payment.grant-results"
    users_service_addr: str = "users_service:8003"

    # YooKassa's published notification-server ranges; requests to
    # /payment/notifications from outside these are ignored. Set
    # verify_webhook_ip=false in .env for local/dev testing.
    verify_webhook_ip: bool = True
    yookassa_notification_cidrs: list[str] = [
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "77.75.154.128/25",
        "2a02:5180::/32",
    ]

    # Reconciliation sweep for payments stuck at `pending`/`grant_requested`.
    stuck_grace_seconds: float = 600
    max_stuck_attempts: int = 10
    reconcile_interval_seconds: float = 300

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
