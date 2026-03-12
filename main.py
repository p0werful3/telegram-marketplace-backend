from hashlib import sha256

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from passlib.context import CryptContext

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
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS city VARCHAR DEFAULT 'Прага'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active'",
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

        conn.execute(
            text(
                """
                UPDATE products
                SET city = 'Прага'
                WHERE city IS NULL OR city = ''
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE products
                SET status = CASE
                    WHEN status IS NOT NULL AND status <> '' THEN status
                    WHEN is_active = TRUE THEN 'active'
                    ELSE 'archived'
                END
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE products
                SET is_active = CASE
                    WHEN status = 'active' THEN TRUE
                    ELSE FALSE
                END
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


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def sync_product_activity(product: models.Product) -> None:
    product.is_active = product.status == "active"


def is_favorite_product(db: Session, user_id: int | None, product_id: int) -> bool:
    if not user_id:
        return False

    favorite = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id,
        models.Favorite.product_id == product_id
    ).first()

    return favorite is not None


def serialize_product(
    db: Session,
    product: models.Product,
    seller: models.User | None,
    current_user_id: int | None = None
):
    return {
        "id": product.id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "category": product.category,
        "condition": product.condition,
        "city": product.city,
        "status": product.status,
        "image_url": product.image_url,
        "is_active": product.is_active,
        "seller_id": product.seller_id,
        "seller_username": seller.username if seller else None,
        "seller_name": seller.full_name if seller else None,
        "seller_telegram_link": f"https://t.me/{seller.username}" if seller and seller.username else None,
        "is_favorite": is_favorite_product(db, current_user_id, product.id),
    }


@app.get("/")
def root():
    return {"message": "Telegram Marketplace API працює"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    username = normalize_text(user.username)
    full_name = normalize_text(user.full_name) if user.full_name else None

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Користувач з таким username вже існує")

    new_user = models.User(
        telegram_id=user.telegram_id,
        username=username,
        full_name=full_name,
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.UserResponse)
def login_user(data: schemas.UserLogin, db: Session = Depends(get_db)):
    username = normalize_text(data.username)
    user = db.query(models.User).filter(models.User.username == username).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Невірний username або password")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Невірний username або password")

    return user


@app.post("/auth/telegram", response_model=schemas.UserResponse)
def telegram_login(data: schemas.TelegramLogin, db: Session = Depends(get_db)):
    username = normalize_text(data.username)
    full_name = normalize_text(data.full_name) if data.full_name else None

    if not username:
        raise HTTPException(status_code=400, detail="У Telegram акаунта немає username")

    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()

    if user:
        user.username = username
        user.full_name = full_name
        db.commit()
        db.refresh(user)
        return user

    existing_username = db.query(models.User).filter(models.User.username == username).first()
    if existing_username:
        existing_username.telegram_id = data.telegram_id
        if full_name:
            existing_username.full_name = full_name
        db.commit()
        db.refresh(existing_username)
        return existing_username

    new_user = models.User(
        telegram_id=data.telegram_id,
        username=username,
        full_name=full_name,
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


@app.get("/users/{user_id}/stats")
def get_user_stats(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    active_count = db.query(models.Product).filter(
        models.Product.seller_id == user_id,
        models.Product.status == "active"
    ).count()

    sold_count = db.query(models.Product).filter(
        models.Product.seller_id == user_id,
        models.Product.status == "sold"
    ).count()

    archived_count = db.query(models.Product).filter(
        models.Product.seller_id == user_id,
        models.Product.status == "archived"
    ).count()

    favorites_count = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id
    ).count()

    cart_count = db.query(models.CartItem).filter(
        models.CartItem.user_id == user_id
    ).count()

    return {
        "active_products": active_count,
        "sold_products": sold_count,
        "archived_products": archived_count,
        "favorites": favorites_count,
        "cart_items": cart_count,
    }


@app.post("/products")
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()

    if not seller:
        raise HTTPException(status_code=404, detail="Продавця не знайдено")

    title = normalize_text(product.title)
    description = normalize_text(product.description)
    category = normalize_text(product.category)
    condition = normalize_text(product.condition)
    city = normalize_text(product.city)
    image_url = normalize_text(product.image_url) if product.image_url else None

    if not title:
        raise HTTPException(status_code=400, detail="Назва товару порожня")
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Назва товару має бути мінімум 2 символи")
    if not description:
        raise HTTPException(status_code=400, detail="Опис товару порожній")
    if len(description) < 5:
        raise HTTPException(status_code=400, detail="Опис товару має бути мінімум 5 символів")
    if not category:
        raise HTTPException(status_code=400, detail="Категорія порожня")
    if condition not in ("Новий", "Б/У"):
        raise HTTPException(status_code=400, detail="Некоректний стан товару")
    if not city:
        raise HTTPException(status_code=400, detail="Місто порожнє")
    if product.price <= 0:
        raise HTTPException(status_code=400, detail="Ціна повинна бути більшою за 0")
    if product.price > 100000000:
        raise HTTPException(status_code=400, detail="Ціна занадто велика")

    new_product = models.Product(
        seller_id=seller.id,
        title=title,
        description=description,
        price=product.price,
        category=category,
        condition=condition,
        city=city,
        status="active",
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
    city: str | None = Query(default=None),
    condition: str | None = Query(default=None),
    sort: str | None = Query(default="newest"),
    current_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db)
):
    query = db.query(models.Product).filter(models.Product.status == "active")

    if q:
        q_clean = normalize_text(q)
        query = query.filter(
            or_(
                models.Product.title.ilike(f"%{q_clean}%"),
                models.Product.description.ilike(f"%{q_clean}%")
            )
        )

    if category and category != "Усі":
        query = query.filter(models.Product.category == category)

    if city and city != "Усі":
        query = query.filter(models.Product.city == city)

    if condition and condition != "Усі":
        query = query.filter(models.Product.condition == condition)

    if sort == "price_asc":
        query = query.order_by(models.Product.price.asc(), models.Product.id.desc())
    elif sort == "price_desc":
        query = query.order_by(models.Product.price.desc(), models.Product.id.desc())
    else:
        query = query.order_by(models.Product.id.desc())

    products = query.all()

    result = []
    for product in products:
        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        result.append(serialize_product(db, product, seller, current_user_id))

    return result


@app.get("/products/{product_id}")
def get_product(
    product_id: int,
    current_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
    return serialize_product(db, product, seller, current_user_id)


@app.get("/users/{user_id}/products")
def get_my_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(
            models.Product.seller_id == user.id,
            models.Product.status == "active"
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
            "city": product.city,
            "status": product.status,
            "image_url": product.image_url,
            "is_active": product.is_active
        })

    return result


@app.get("/users/{user_id}/products/sold")
def get_my_sold_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(
            models.Product.seller_id == user.id,
            models.Product.status == "sold"
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
            "city": product.city,
            "status": product.status,
            "image_url": product.image_url,
            "is_active": product.is_active
        })

    return result


@app.get("/users/{user_id}/products/archived")
def get_my_archived_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    products = (
        db.query(models.Product)
        .filter(
            models.Product.seller_id == user.id,
            models.Product.status == "archived"
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
            "city": product.city,
            "status": product.status,
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
            models.Product.status.in_(["sold", "archived"])
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
            "city": product.city,
            "status": product.status,
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

    product.status = "archived"
    sync_product_activity(product)

    db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()
    db.query(models.Favorite).filter(models.Favorite.product_id == product.id).delete()

    db.commit()

    return {"message": "Оголошення перенесено в архів"}


@app.post("/cart/add")
def add_to_cart(data: schemas.CartAdd, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not product or product.status != "active":
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

    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == user.id).order_by(models.CartItem.id.desc()).all()

    result = []
    total = 0
    stale_cart_item_ids = []

    for item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()

        if not product or product.status != "active":
            stale_cart_item_ids.append(item.id)
            continue

        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        total += product.price
        result.append({
            "cart_item_id": item.id,
            "product_id": product.id,
            "title": product.title,
            "price": product.price,
            "image_url": product.image_url,
            "seller_username": seller.username if seller else None,
            "seller_link": f"https://t.me/{seller.username}" if seller and seller.username else None
        })

    if stale_cart_item_ids:
        db.query(models.CartItem).filter(models.CartItem.id.in_(stale_cart_item_ids)).delete(synchronize_session=False)
        db.commit()

    return {"items": result, "total": total}


@app.delete("/cart/items/{cart_item_id}")
def remove_cart_item(cart_item_id: int, user_id: int = Query(...), db: Session = Depends(get_db)):
    cart_item = db.query(models.CartItem).filter(models.CartItem.id == cart_item_id).first()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Елемент кошика не знайдено")

    if cart_item.user_id != user_id:
        raise HTTPException(status_code=403, detail="Це не ваш кошик")

    db.delete(cart_item)
    db.commit()

    return {"message": "Товар видалено з кошика"}


@app.post("/orders/buy")
def buy_product(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    buyer = db.query(models.User).filter(models.User.id == data.buyer_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()

    if not buyer:
        raise HTTPException(status_code=404, detail="Покупця не знайдено")

    if not product or product.status != "active":
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

    product.status = "sold"
    sync_product_activity(product)

    db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()
    db.query(models.Favorite).filter(models.Favorite.product_id == product.id).delete()

    db.commit()

    return {
        "message": "Покупку оформлено",
        "seller_username": seller_username,
        "seller_link": seller_link
    }


@app.post("/favorites")
def add_to_favorites(data: schemas.FavoriteCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user.id,
        models.Favorite.product_id == product.id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Товар уже в обраному")

    favorite = models.Favorite(user_id=user.id, product_id=product.id)
    db.add(favorite)
    db.commit()

    return {"message": "Товар додано в обране"}


@app.delete("/favorites")
def remove_from_favorites(user_id: int = Query(...), product_id: int = Query(...), db: Session = Depends(get_db)):
    favorite = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id,
        models.Favorite.product_id == product_id
    ).first()

    if not favorite:
        raise HTTPException(status_code=404, detail="Товар не знайдено в обраному")

    db.delete(favorite)
    db.commit()

    return {"message": "Товар видалено з обраного"}


@app.get("/favorites/{user_id}")
def get_favorites(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    favorites = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id
    ).order_by(models.Favorite.id.desc()).all()

    result = []
    stale_favorite_ids = []

    for favorite in favorites:
        product = db.query(models.Product).filter(models.Product.id == favorite.product_id).first()

        if not product or product.status != "active":
            stale_favorite_ids.append(favorite.id)
            continue

        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        result.append(serialize_product(db, product, seller, user_id))

    if stale_favorite_ids:
        db.query(models.Favorite).filter(models.Favorite.id.in_(stale_favorite_ids)).delete(synchronize_session=False)
        db.commit()

    return result
