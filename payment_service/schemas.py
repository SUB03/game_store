from pydantic import BaseModel


class CartItem(BaseModel):
    appid: int


class LibraryGame(BaseModel):
    appid: int


class CheckoutRequest(BaseModel):
    idempotency_key: str


class Price(BaseModel):
    price: float
