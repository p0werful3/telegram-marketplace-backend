from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    telegram_id: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class TelegramLogin(BaseModel):
    telegram_id: str
    username: str | None = None
    full_name: str | None = None


class UserResponse(BaseModel):
    id: int
    telegram_id: str | None = None
    username: str
    full_name: str | None = None

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    seller_id: int
    title: str
    description: str
    price: float
    category: str
    image_url: str | None = None


class CartAdd(BaseModel):
    user_id: int
    product_id: int


class OrderCreate(BaseModel):
    buyer_id: int
    product_id: int
