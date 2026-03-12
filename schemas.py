from typing import Optional, Literal, List
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
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=5, max_length=3000)
    price: float
    currency: Literal["USD", "UAH", "EUR"]
    category: str = Field(min_length=1, max_length=100)
    condition: Literal["Новий", "Б/У"]
    city: str = Field(min_length=1, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    image_urls: List[str] = Field(default_factory=list, max_length=10)


class ProductResponse(BaseModel):
    id: int
    title: str
    description: str
    price: float
    currency: str
    category: str
    condition: str
    city: str
    status: str
    image_url: Optional[str]
    image_urls: List[str] = []
    is_active: bool
    seller_id: int
    seller_username: Optional[str]
    seller_name: Optional[str]
    seller_telegram_link: Optional[str]
    is_favorite: bool = False

    class Config:
        from_attributes = True


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int


class FavoriteCreate(BaseModel):
    user_id: int
    product_id: int
