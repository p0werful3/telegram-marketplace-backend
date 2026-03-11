from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import engine, get_db
import models
import schemas

app = FastAPI(title="Telegram Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://p0werful3.github.io",
        "https://telegram-marketplace-api.onrender.com",
        "https://web.telegram.org",
        "https://web.telegram.org.a",
        "*",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

models.Base.metadata.create_all(bind=engine)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


@app.get("/")
def root():
    return {"message": "Telegram Marketplace API працює"}


@app.post("/auth/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Користувач з таким username вже існує")

    new_user = models.User(
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name,
        password_hash=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.UserResponse)
def login_user(data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Невірний username або password")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Невірний username або password")

    return user


@app.post("/auth/telegram", response_model=schemas.UserResponse)
def telegram_login(data: schemas.TelegramLogin, db: Session = Depends(get_db)):
    if not data.username:
        raise HTTPException(status_code=400, detail="У Telegram акаунта немає username")

    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()

    if user:
        user.username = data.username
        user.full_name = data.full_name
        db.commit()
        db.refresh(user)
        return user

    existing_username = db.query(models.User).filter(models.User.username == data.username).first()
    if existing_username:
        existing_username.telegram_id = data.telegram_id
        if data.full_name:
            existing_username.full_name = data.full_name
        db.commit()
        db.refresh(existing_username)
        return existing_username

    new_user = models.User(
        telegram_id=data.telegram_id,
        username=data.username,
        full_name=data.full_name,
        password_hash=None
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return user


@app.post("/products")
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()

    if not seller:
        raise HTTPException(status_code=404, detail="Продавця не знайдено")

    new_product = models.Product(
        seller_id=seller.id,
        title=product.title,
        description=product.description,
        price=product.price,
        category=product.category,
        image_url=product.image_url
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return {"message": "Товар створено", "product_id": new_product.id}


@app.get("/products")
def get_products(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db)
):
    query = db.query(models.Product).filter(models.Product.is_active == True)

    if q:
        query = query.filter(models.Product.title.ilike(f"%{q}%"))

    if category and category != "Усі":
        query = query.filter(models.Product.category == category)

    products = query.order_by(models.Product.id.desc()).all()

    result = []
    for product in products:
        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        result.append({
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "price": product.price,
            "category": product.category,
            "image_url": product.image_url,
            "seller_username": seller.username if seller else None,
            "seller_name": seller.full_name if seller else None,
            "seller_telegram_link": f"https://t.me/{seller.username}" if seller and seller.username else None
        })

    return result


@app.get("/users/{user_id}/products")
def get_my_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(models.Product.seller_id == user.id)
        .order_by(models.Product.id.desc())
        .all()
    )

    result = []
    for product in products:
        result.append({
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "price": product.price,
            "category": product.category,
            "image_url": product.image_url,
            "is_active": product.is_active
        })

    return result


@app.delete("/products/{product_id}")
def delete_product(product_id: int, user_id: int = Query(...), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    if product.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Це не ваше оголошення")

    product.is_active = False
    db.commit()

    return {"message": "Оголошення видалено"}


@app.post("/cart/add")
def add_to_cart(data: schemas.CartAdd, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    cart_item = models.CartItem(user_id=user.id, product_id=product.id)
    db.add(cart_item)
    db.commit()

    return {"message": "Товар додано до кошика"}


@app.get("/cart/{user_id}")
def get_cart(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == user.id).all()

    result = []
    total = 0

    for item in cart_items:
        product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.is_active == True
        ).first()

        if product:
            seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
            total += product.price
            result.append({
                "cart_item_id": item.id,
                "product_id": product.id,
                "title": product.title,
                "price": product.price,
                "seller_username": seller.username if seller else None,
                "seller_link": f"https://t.me/{seller.username}" if seller and seller.username else None
            })

    return {"items": result, "total": total}


@app.post("/orders/buy")
def buy_product(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    buyer = db.query(models.User).filter(models.User.id == data.buyer_id).first()
    product = db.query(models.Product).filter(
        models.Product.id == data.product_id,
        models.Product.is_active == True
    ).first()

    if not buyer:
        raise HTTPException(status_code=404, detail="Покупця не знайдено")

    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()

    seller_username = seller.username if seller else None
    seller_link = f"https://t.me/{seller_username}" if seller_username else None

    order = models.Order(
        buyer_id=buyer.id,
        product_id=product.id,
        seller_username=seller_username,
        seller_link=seller_link
    )

    db.add(order)
    db.commit()

    return {
        "message": "Покупку оформлено",
        "seller_username": seller_username,
        "seller_link": seller_link
    }
