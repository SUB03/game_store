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
        
        async with YooKassaClient(
            account_id=self.settings.shopid,
            secret_key=self.settings.ukass_api_key
        ) as client:
            yookassa_request = PaymentRequest(
                amount=Amount(value=request.price, currency="RUB"),
                description=f"Purchase of app {request.appid} by {request.username}",
                capture=True,
                metadata={
                    "username": request.username,
                    "appid": str(request.appid),
                },
                confirmation=RedirectConfirmationRequest(
                    type="redirect",
                    return_url=f"{self.settings.frontend_url}/app/{request.appid}"
                )
            )

            payment = await client.payment.create(yookassa_request)
            

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