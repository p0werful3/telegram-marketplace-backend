from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    telegram_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TelegramLogin(BaseModel):
    telegram_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    init_data: Optional[str] = None


class UserProfileUpdate(BaseModel):
    username: str
    full_name: Optional[str] = None
    password: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[str] = None
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool = False
    is_superadmin: bool = False
    is_banned: bool = False
    rating_sum: float = 0
    rating_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    seller_id: int
    title: str
    description: str
    price: float
    currency: Optional[str] = "USD"
    category: str
    condition: str
    city: str
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class FavoriteCreate(BaseModel):
    user_id: int
    product_id: int


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int


class OrderDecision(BaseModel):
    seller_id: int
    approve: bool


class ReviewCreate(BaseModel):
    buyer_id: int
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class SuggestionCreate(BaseModel):
    user_id: int
    title: str
    message: str


class SuggestionStatusUpdate(BaseModel):
    status: str


class ReportCreate(BaseModel):
    reporter_id: int
    listing_id: int
    reason: str
    comment: Optional[str] = None


class ReportStatusUpdate(BaseModel):
    status: str
