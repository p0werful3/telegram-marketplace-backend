from typing import Optional, Literal, List
from pydantic import BaseModel, Field


CurrencyType = Literal["USD", "UAH", "EUR"]
ConditionType = Literal["Новий", "Б/У"]


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


class UserProfileUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, min_length=4, max_length=128)


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[str] = None
    username: str
    full_name: Optional[str] = None

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    seller_id: int
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=5, max_length=3000)
    price: float
    currency: CurrencyType = "USD"
    category: str = Field(min_length=1, max_length=100)
    condition: ConditionType
    city: str = Field(min_length=1, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    image_urls: List[str] = Field(default_factory=list)


class ProductUpdate(ProductCreate):
    pass


class ProductResponse(BaseModel):
    id: int
    title: str
    description: str
    price: float
    currency: CurrencyType = "USD"
    category: str
    condition: str
    city: str
    status: str
    image_url: Optional[str] = None
    image_urls: List[str] = []
    is_active: bool
    seller_id: int
    seller_username: Optional[str] = None
    seller_name: Optional[str] = None
    seller_telegram_link: Optional[str] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int


class OrderDecision(BaseModel):
    seller_id: int
    approve: bool


class FavoriteCreate(BaseModel):
    user_id: int
    product_id: int
