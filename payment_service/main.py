import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

import grpc, asyncio
import payment_proto.payment_service_pb2 as payment_service_pb2
import payment_proto.payment_service_pb2_grpc as payment_service_pb2_grpc

from async_yookassa import YooKassaClient
from async_yookassa.models.payment import PaymentRequest, Amount, RedirectConfirmationRequest

class Settings(BaseSettings):
    shopid: str
    ukass_api_key: str = Field(alias="UKASS_API_KEY")
    frontend_url: str = Field(alias="FRONTEND_URL")
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

class PaymentServiceServicer(payment_service_pb2_grpc.PaymentServiceServicer):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def MakePayment(
            self,
            request: payment_service_pb2.MakePaymentRequest,
            context: grpc.aio.ServicerContext
    ) -> payment_service_pb2.MakePaymentResponse:
        # Cart checkout fills appids (+ the cart's idempotency key); the
        # legacy single-game purchase only fills appid.
        appids = list(request.appids) or [request.appid]
        if len(appids) > 1:
            description = f"Purchase of {len(appids)} games by {request.username}"
            return_url = f"{self.settings.frontend_url}/profile"
        else:
            description = f"Purchase of app {appids[0]} by {request.username}"
            return_url = f"{self.settings.frontend_url}/app/{appids[0]}"

        # The webhook reads these to grant ownership of every paid game.
        metadata = {
            "username": request.username,
            "appid": str(appids[0]),
            "appids": ",".join(str(appid) for appid in appids),
        }

        idempotency_key = None
        if request.idempotency_key:
            try:
                idempotency_key = uuid.UUID(request.idempotency_key)
            except ValueError:
                # Never fail a payment over a malformed key; the library
                # generates a fresh random one when None is passed.
                idempotency_key = None

        async with YooKassaClient(
            account_id=self.settings.shopid,
            secret_key=self.settings.ukass_api_key
        ) as client:
            yookassa_request = PaymentRequest(
                amount=Amount(value=request.price, currency="RUB"),
                description=description,
                capture=True,
                metadata=metadata,
                confirmation=RedirectConfirmationRequest(
                    type="redirect",
                    return_url=return_url
                )
            )

            payment = await client.payment.create(
                yookassa_request, idempotency_key=idempotency_key
            )
            

        return payment_service_pb2.MakePaymentResponse(
            payment_id=payment.id,
            confirmation_url=payment.confirmation.confirmation_url
        )


async def serve():
    settings = Settings()

    server = grpc.aio.server()
    payment_service_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentServiceServicer(settings), server)
    server.add_insecure_port('[::]:8002')

    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())