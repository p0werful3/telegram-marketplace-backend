from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    telegram_id: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TelegramLogin(BaseModel):
    telegram_id: str
    username: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[str]
    username: str
    full_name: Optional[str]

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    seller_id: int
    title: str
    description: str
    price: float
    category: str
    image_url: Optional[str] = None


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int
