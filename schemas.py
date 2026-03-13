
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str
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
    telegram_id: Optional[str] = None
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool = False
    is_banned: bool = False
    rating_sum: float = 0
    rating_count: int = 0

    class Config:
        orm_mode = True


class UserProfileUpdate(BaseModel):
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None


class ProductBase(BaseModel):
    seller_id: int
    title: str
    description: str
    price: float
    currency: str = "USD"
    category: str
    condition: str = "Новий"
    city: str = "Київ"
    image_url: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int


class OrderDecision(BaseModel):
    seller_id: int
    approve: bool


class OrderCancel(BaseModel):
    buyer_id: int


class FavoriteCreate(BaseModel):
    user_id: int
    product_id: int


class ReviewCreate(BaseModel):
    buyer_id: int
    rating: int
    comment: Optional[str] = None

    @validator("rating")
    def validate_rating(cls, value: int) -> int:
        if value < 1 or value > 5:
            raise ValueError("Rating має бути від 1 до 5")
        return value


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
