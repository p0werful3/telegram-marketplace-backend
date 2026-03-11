from pydantic import BaseModel


class UserCreate(BaseModel):
    telegram_id: str
    username: str | None = None
    full_name: str


class UserResponse(BaseModel):
    id: int
    telegram_id: str
    username: str | None = None
    full_name: str

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    seller_telegram_id: str
    title: str
    description: str
    price: float
    category: str
    image_url: str | None = None


class ProductResponse(BaseModel):
    id: int
    seller_id: int
    title: str
    description: str
    price: float
    category: str
    image_url: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class CartAdd(BaseModel):
    user_telegram_id: str
    product_id: int


class OrderCreate(BaseModel):
    buyer_telegram_id: str
    product_id: int