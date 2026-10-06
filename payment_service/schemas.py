from pydantic import BaseModel


class PurchaseGame(BaseModel):
    appid: int


class CartItem(BaseModel):
    appid: int


class LibraryGame(BaseModel):
    appid: int


class Price(BaseModel):
    price: float
