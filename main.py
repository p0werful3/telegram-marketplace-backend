from hashlib import sha256

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from sqlalchemy import text

from database import engine, get_db
import models
import schemas

app = FastAPI(title="Telegram Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://p0werful3.github.io",
        "https://telegram.org",
        "https://web.telegram.org",
        "https://t.me",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

models.Base.metadata.create_all(bind=engine)


def run_safe_migrations() -> None:
    queries = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url VARCHAR",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS condition VARCHAR DEFAULT 'Новий'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_username VARCHAR",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_link VARCHAR",
    ]

    with engine.begin() as conn:
        for query in queries:
            conn.execute(text(query))

        conn.execute(
            text(
                """
                UPDATE products
                SET condition = 'Новий'
                WHERE condition IS NULL OR condition = ''
                """
            )
        )


run_safe_migrations()


def normalize_password(password: str) -> str:
    if password is None:
        raise HTTPException(status_code=400, detail="Password обов'язковий")

    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password має бути мінімум 4 символи")

    return sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    normalized = normalize_password(password)
    return pwd_context.hash(normalized)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        if pwd_context.verify(password, password_hash):
            return True
    except Exception:
        pass

    try:
        normalized = normalize_password(password)
        return pwd_context.verify(normalized, password_hash)
    except Exception:
        return False


def serialize_product(product: models.Product, seller: models.User | None):
    return {
        "id": product.id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "category": product.category,
        "condition": product.condition,
        "image_url": product.image_url,
        "is_active": product.is_active,
        "seller_id": product.seller_id,
        "seller_username": seller.username if seller else None,
        "seller_name": seller.full_name if seller else None,
        "seller_telegram_link": f"https://t.me/{seller.username}" if seller and seller.username else None,
    }


@app.get("/")
def root():
    return {"message": "Telegram Marketplace API працює"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Користувач з таким username вже існує")

    new_user = models.User(
        telegram_id=user.telegram_id,
        username=user.username.strip(),
        full_name=user.full_name.strip() if user.full_name else None,
        password_hash=hash_password(user.password),
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
        user.username = data.username.strip()
        user.full_name = data.full_name.strip() if data.full_name else None
        db.commit()
        db.refresh(user)
        return user

    existing_username = db.query(models.User).filter(models.User.username == data.username).first()
    if existing_username:
        existing_username.telegram_id = data.telegram_id
        if data.full_name:
            existing_username.full_name = data.full_name.strip()
        db.commit()
        db.refresh(existing_username)
        return existing_username

    new_user = models.User(
        telegram_id=data.telegram_id,
        username=data.username.strip(),
        full_name=data.full_name.strip() if data.full_name else None,
        password_hash=None,
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

    title = product.title.strip()
    description = product.description.strip()
    category = product.category.strip()
    condition = product.condition.strip()
    image_url = product.image_url.strip() if product.image_url else None

    if not title:
        raise HTTPException(status_code=400, detail="Назва товару порожня")
    if not description:
        raise HTTPException(status_code=400, detail="Опис товару порожній")
    if not category:
        raise HTTPException(status_code=400, detail="Категорія порожня")
    if condition not in ("Новий", "Б/У"):
        raise HTTPException(status_code=400, detail="Некоректний стан товару")
    if product.price <= 0:
        raise HTTPException(status_code=400, detail="Ціна повинна бути більшою за 0")

    new_product = models.Product(
        seller_id=seller.id,
        title=title,
        description=description,
        price=product.price,
        category=category,
        condition=condition,
        image_url=image_url,
        is_active=True,
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
        result.append(serialize_product(product, seller))

    return result


@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
    return serialize_product(product, seller)


@app.get("/users/{user_id}/products")
def get_my_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(
            models.Product.seller_id == user.id,
            models.Product.is_active == True
        )
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
            "condition": product.condition,
            "image_url": product.image_url,
            "is_active": product.is_active
        })

    return result


@app.get("/users/{user_id}/products/history")
def get_my_products_history(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(
            models.Product.seller_id == user.id,
            models.Product.is_active == False
        )
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
            "condition": product.condition,
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

    db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()

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

    if product.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Не можна додати в кошик власний товар")

    existing_cart_item = db.query(models.CartItem).filter(
        models.CartItem.user_id == user.id,
        models.CartItem.product_id == product.id
    ).first()

    if existing_cart_item:
        raise HTTPException(status_code=400, detail="Цей товар уже є в кошику")

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
    stale_cart_item_ids = []

    for item in cart_items:
        product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.is_active == True
        ).first()

        if not product:
            stale_cart_item_ids.append(item.id)
            continue

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

    if stale_cart_item_ids:
        db.query(models.CartItem).filter(models.CartItem.id.in_(stale_cart_item_ids)).delete(synchronize_session=False)
        db.commit()

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

    if product.seller_id == buyer.id:
        raise HTTPException(status_code=400, detail="Не можна купити власний товар")

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

    product.is_active = False

    db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()

    db.commit()

    return {
        "message": "Покупку оформлено",
        "seller_username": seller_username,
        "seller_link": seller_link
    }
