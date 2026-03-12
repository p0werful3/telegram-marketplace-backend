from typing import Optional
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=100)
    telegram_id: Optional[str] = Field(default=None, max_length=50)


class UserLogin(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=128)


class TelegramLogin(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = Field(default=None, max_length=100)


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[str]
    username: str
    full_name: Optional[str]

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    seller_id: int
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=3000)
    price: float
    category: str = Field(min_length=1, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=1000)


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int
