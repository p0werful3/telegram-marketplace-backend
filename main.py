from datetime import datetime
from hashlib import sha256
from urllib.parse import parse_qsl
from urllib.request import Request as URLRequest, urlopen
from urllib.error import URLError, HTTPError
import json
import os

from fastapi import FastAPI, Depends, HTTPException, Query, Request as FastAPIRequest
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
ALLOWED_CURRENCIES = {"USD", "UAH", "EUR"}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://p0werful3.github.io/telegram-marketplace-miniapp/?v=401")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def run_safe_migrations() -> None:
    queries = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_sum FLOAT DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0",

        "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url VARCHAR",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS condition VARCHAR DEFAULT 'Новий'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS city VARCHAR DEFAULT 'Київ'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS currency VARCHAR DEFAULT 'USD'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS views_count INTEGER DEFAULT 0",

        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_username VARCHAR",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type VARCHAR DEFAULT 'info'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_order_id INTEGER",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_product_id INTEGER",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_link VARCHAR",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_id INTEGER",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS offered_price FLOAT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS currency VARCHAR DEFAULT 'USD'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_username VARCHAR",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_full_name VARCHAR",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_response_at TIMESTAMP WITH TIME ZONE",
    ]

    with engine.begin() as conn:
        for query in queries:
            conn.execute(text(query))

        conn.execute(text("UPDATE users SET is_admin=FALSE WHERE is_admin IS NULL"))
        conn.execute(text("UPDATE users SET is_superadmin=FALSE WHERE is_superadmin IS NULL"))
        conn.execute(text("UPDATE users SET is_banned=FALSE WHERE is_banned IS NULL"))
        conn.execute(text("UPDATE users SET is_admin=TRUE WHERE username='powerfull_2' OR telegram_id='powerfull_2'"))
        conn.execute(text("UPDATE users SET is_superadmin=TRUE WHERE username='powerfull_2' OR telegram_id='powerfull_2'"))
        conn.execute(text("UPDATE users SET rating_sum=0 WHERE rating_sum IS NULL"))
        conn.execute(text("UPDATE users SET rating_count=0 WHERE rating_count IS NULL"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER UNIQUE NOT NULL REFERENCES orders(id),
                    seller_id INTEGER NOT NULL REFERENCES users(id),
                    buyer_id INTEGER NOT NULL REFERENCES users(id),
                    rating INTEGER NOT NULL,
                    comment VARCHAR,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS product_views (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(user_id, product_id)
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id SERIAL PRIMARY KEY,
                    admin_id INTEGER NOT NULL REFERENCES users(id),
                    action VARCHAR NOT NULL,
                    target_type VARCHAR,
                    target_id INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS suggestions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title VARCHAR NOT NULL,
                    message VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'new',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title VARCHAR NOT NULL,
                    message VARCHAR NOT NULL,
                    type VARCHAR NOT NULL DEFAULT 'info',
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    related_order_id INTEGER REFERENCES orders(id),
                    related_product_id INTEGER REFERENCES products(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id SERIAL PRIMARY KEY,
                    reporter_id INTEGER NOT NULL REFERENCES users(id),
                    listing_id INTEGER NOT NULL REFERENCES products(id),
                    reason VARCHAR NOT NULL,
                    comment VARCHAR,
                    status VARCHAR NOT NULL DEFAULT 'new',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(text("UPDATE products SET condition='Новий' WHERE condition IS NULL OR condition=''"))
        conn.execute(text("UPDATE products SET city='Київ' WHERE city IS NULL OR city=''"))
        conn.execute(text("UPDATE products SET currency='USD' WHERE currency IS NULL OR currency=''"))
        conn.execute(text("UPDATE orders SET currency='USD' WHERE currency IS NULL OR currency=''"))

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
                SET is_active = CASE WHEN status = 'active' THEN TRUE ELSE FALSE END
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE orders o
                SET seller_id = p.seller_id,
                    offered_price = p.price,
                    buyer_username = u.username,
                    buyer_full_name = u.full_name,
                    status = COALESCE(NULLIF(o.status, ''), 'approved')
                FROM products p, users u
                WHERE o.product_id = p.id AND o.buyer_id = u.id
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
    return pwd_context.hash(normalize_password(password))


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        if pwd_context.verify(password, password_hash):
            return True
    except Exception:
        pass
    try:
        return pwd_context.verify(normalize_password(password), password_hash)
    except Exception:
        return False


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def rating_value(user: models.User | None) -> float:
    if not user or not user.rating_count:
        return 0.0
    return round((user.rating_sum or 0) / user.rating_count, 2)


def seller_badge(sold_products: int, review_count: int) -> str:
    sold_products = sold_products or 0
    review_count = review_count or 0
    if sold_products >= 10:
        return "Топ продавець"
    if sold_products >= 3 and review_count >= 3:
        return "Надійний продавець"
    return "Новий продавець"


def create_notification(db: Session, user_id: int, title: str, message: str, type_: str = "info", related_order_id: int | None = None, related_product_id: int | None = None) -> None:
    db.add(models.Notification(
        user_id=user_id,
        title=normalize_text(title) or "Сповіщення",
        message=normalize_text(message) or "Нова подія",
        type=type_ or "info",
        related_order_id=related_order_id,
        related_product_id=related_product_id,
        is_read=False,
    ))


def _is_real_telegram_id(value: str | None) -> bool:
    raw = normalize_text(value)
    return raw.isdigit() if raw else False


def send_telegram_message(telegram_id: str | None, text_message: str, button_text: str = "Відкрити маркетплейс") -> bool:
    if not TELEGRAM_BOT_TOKEN or not _is_real_telegram_id(telegram_id):
        return False

    payload = {
        "chat_id": str(telegram_id),
        "text": text_message,
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [[{
                "text": button_text,
                "web_app": {"url": WEBAPP_URL}
            }]]
        }
    }

    try:
        request = URLRequest(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except (HTTPError, URLError, TimeoutError, Exception) as exc:
        print(f"Telegram send error: {exc}")
        return False


def notify_user_in_telegram(user: models.User | None, text_message: str, button_text: str = "Відкрити маркетплейс") -> bool:
    if not user:
        return False
    return send_telegram_message(getattr(user, "telegram_id", None), text_message, button_text)


def is_product_in_cart(db: Session, user_id: int | None, product_id: int) -> bool:
    if not user_id:
        return False
    return db.query(models.CartItem).filter(
        models.CartItem.user_id == user_id,
        models.CartItem.product_id == product_id,
    ).first() is not None

def ensure_not_banned(user: models.User | None) -> None:
    if user and user.is_banned:
        raise HTTPException(status_code=403, detail="Користувача заблоковано")


def require_admin(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Адміністратора не знайдено")
    ensure_not_banned(user)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Немає доступу до адмінки")
    return user




def is_superadmin_user(user: models.User | None) -> bool:
    if not user:
        return False
    return bool(getattr(user, "is_superadmin", False) or normalize_text(getattr(user, "username", "")) == "powerfull_2" or normalize_text(getattr(user, "telegram_id", "")) == "powerfull_2")


def require_superadmin(db: Session, user_id: int) -> models.User:
    user = require_admin(db, user_id)
    if not is_superadmin_user(user):
        raise HTTPException(status_code=403, detail="Лише суперадмін може виконати цю дію")
    return user

def log_admin_action(db: Session, admin_id: int, action: str, target_type: str | None = None, target_id: int | None = None) -> None:
    db.add(models.AdminLog(admin_id=admin_id, action=action, target_type=target_type, target_id=target_id))
    db.commit()


def normalize_currency(value: str | None) -> str:
    currency = normalize_text(value).upper() or "USD"
    if currency not in ALLOWED_CURRENCIES:
        raise HTTPException(status_code=400, detail="Некоректна валюта")
    return currency


def ensure_unique_username(db: Session, username: str, exclude_user_id: int | None = None) -> str:
    normalized = normalize_text(username)
    if len(normalized) < 3:
        raise HTTPException(status_code=400, detail="Username має бути мінімум 3 символи")
    existing = db.query(models.User).filter(models.User.username == normalized).first()
    if existing and existing.id != exclude_user_id:
        raise HTTPException(status_code=400, detail="Користувач з таким username вже існує")
    return normalized


def sync_product_activity(product: models.Product) -> None:
    product.is_active = product.status == "active"


def get_product_images(db: Session, product_id: int) -> list[str]:
    images = (
        db.query(models.ProductImage)
        .filter(models.ProductImage.product_id == product_id)
        .order_by(models.ProductImage.sort_order.asc(), models.ProductImage.id.asc())
        .all()
    )
    return [img.image_url for img in images]


def replace_product_images(db: Session, product_id: int, image_urls: list[str]) -> None:
    db.query(models.ProductImage).filter(models.ProductImage.product_id == product_id).delete()
    for idx, url in enumerate(image_urls):
        db.add(models.ProductImage(product_id=product_id, image_url=url, sort_order=idx))


def is_favorite_product(db: Session, user_id: int | None, product_id: int) -> bool:
    if not user_id:
        return False
    favorite = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id,
        models.Favorite.product_id == product_id,
    ).first()
    return favorite is not None


def serialize_product(db: Session, product: models.Product, seller: models.User | None, current_user_id: int | None = None):
    image_urls = get_product_images(db, product.id)
    fallback_first = product.image_url if product.image_url else (image_urls[0] if image_urls else None)
    if not image_urls and fallback_first:
        image_urls = [fallback_first]
    return {
        "id": product.id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "currency": product.currency or "USD",
        "category": product.category,
        "condition": product.condition,
        "city": product.city,
        "status": product.status,
        "image_url": fallback_first,
        "image_urls": image_urls,
        "is_active": product.is_active,
        "seller_id": product.seller_id,
        "seller_username": seller.username if seller else None,
        "seller_name": seller.full_name if seller else None,
        "seller_telegram_link": f"https://t.me/{seller.username}" if seller and seller.username else None,
        "seller_rating": rating_value(seller) if seller else 0,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "views_count": int(getattr(product, "views_count", 0) or 0),
        "is_favorite": is_favorite_product(db, current_user_id, product.id),
        "is_in_cart": is_product_in_cart(db, current_user_id, product.id),
    }


def validate_and_prepare_product_payload(payload: schemas.ProductCreate | schemas.ProductUpdate):
    title = normalize_text(payload.title)
    description = normalize_text(payload.description)
    category = normalize_text(payload.category)
    condition = normalize_text(payload.condition)
    city = normalize_text(payload.city)
    currency = normalize_currency(payload.currency)

    image_urls = [normalize_text(url) for url in (payload.image_urls or []) if normalize_text(url)]
    if payload.image_url and normalize_text(payload.image_url) not in image_urls:
        image_urls.insert(0, normalize_text(payload.image_url))

    if len(image_urls) > 10:
        raise HTTPException(status_code=400, detail="Можна додати максимум 10 фото")
    if not title or len(title) < 2:
        raise HTTPException(status_code=400, detail="Назва товару має бути мінімум 2 символи")
    if not description or len(description) < 5:
        raise HTTPException(status_code=400, detail="Опис товару має бути мінімум 5 символів")
    if not category:
        raise HTTPException(status_code=400, detail="Категорія порожня")
    if condition not in ("Новий", "Б/У"):
        raise HTTPException(status_code=400, detail="Некоректний стан товару")
    if not city:
        raise HTTPException(status_code=400, detail="Місто порожнє")
    if payload.price <= 0:
        raise HTTPException(status_code=400, detail="Ціна повинна бути більшою за 0")
    if payload.price > 100000000:
        raise HTTPException(status_code=400, detail="Ціна занадто велика")

    return {
        "title": title,
        "description": description,
        "price": payload.price,
        "currency": currency,
        "category": category,
        "condition": condition,
        "city": city,
        "image_urls": image_urls,
        "first_image": image_urls[0] if image_urls else None,
    }


def _serialize_simple_my_product(product: models.Product, db: Session):
    image_urls = get_product_images(db, product.id) or ([product.image_url] if product.image_url else [])
    latest_pending_order = db.query(models.Order).filter(
        models.Order.product_id == product.id,
        models.Order.status == "pending"
    ).order_by(models.Order.id.desc()).first()
    approved_order = db.query(models.Order).filter(
        models.Order.product_id == product.id,
        models.Order.status == "approved"
    ).order_by(models.Order.id.desc()).first()

    return {
        "id": product.id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "currency": product.currency or "USD",
        "category": product.category,
        "condition": product.condition,
        "city": product.city,
        "status": product.status,
        "image_url": product.image_url,
        "image_urls": image_urls,
        "is_active": product.is_active,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "pending_requests_count": db.query(models.Order).filter(
            models.Order.product_id == product.id,
            models.Order.status == "pending"
        ).count(),
        "latest_request": {
            "order_id": latest_pending_order.id,
            "created_at": latest_pending_order.created_at.isoformat() if latest_pending_order and latest_pending_order.created_at else None,
            "buyer_id": latest_pending_order.buyer_id if latest_pending_order else None,
            "buyer_username": latest_pending_order.buyer_username if latest_pending_order else None,
            "buyer_full_name": latest_pending_order.buyer_full_name if latest_pending_order else None,
            "offered_price": latest_pending_order.offered_price if latest_pending_order else None,
            "currency": latest_pending_order.currency if latest_pending_order else None,
        } if latest_pending_order else None,
        "sale_info": {
            "order_id": approved_order.id,
            "sold_at": approved_order.seller_response_at.isoformat() if approved_order and approved_order.seller_response_at else None,
            "buyer_id": approved_order.buyer_id if approved_order else None,
            "buyer_username": approved_order.buyer_username if approved_order else None,
            "buyer_full_name": approved_order.buyer_full_name if approved_order else None,
            "offered_price": approved_order.offered_price if approved_order else None,
            "currency": approved_order.currency if approved_order else None,
        } if approved_order else None,
    }


@app.get("/")
def root():
    return {"message": "Telegram Marketplace API працює"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    username = ensure_unique_username(db, user.username)
    full_name = normalize_text(user.full_name) if user.full_name else None
    new_user = models.User(
        telegram_id=user.telegram_id,
        username=username,
        full_name=full_name,
        password_hash=hash_password(user.password),
    )
    if username == 'powerfull_2':
        new_user.is_admin = True
        new_user.is_superadmin = True
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.UserResponse)
def login_user(data: schemas.UserLogin, db: Session = Depends(get_db)):
    username = normalize_text(data.username)
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Невірний username або password")
    ensure_not_banned(user)
    return user


def parse_telegram_init_data(init_data: str | None) -> dict:
    if not init_data:
        return {}
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return {}

    user_raw = parsed.get("user")
    if not user_raw:
        return parsed

    try:
        user_obj = json.loads(user_raw)
        if isinstance(user_obj, dict):
            parsed["user_obj"] = user_obj
    except Exception:
        pass
    return parsed


def upsert_telegram_user(db: Session, telegram_id: str | None, username: str | None, full_name: str | None):
    telegram_id = normalize_text(telegram_id)
    username = normalize_text(username).lstrip("@")
    full_name = normalize_text(full_name) or None

    if not telegram_id or not telegram_id.isdigit():
        raise HTTPException(status_code=400, detail="Некоректний Telegram ID")

    user = None
    if username:
        user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()

    if user:
        user.telegram_id = telegram_id
        if username:
            user.username = username
        if full_name:
            user.full_name = full_name
        if username == 'powerfull_2' or telegram_id == 'powerfull_2':
            user.is_admin = True
            user.is_superadmin = True
        db.commit()
        db.refresh(user)
        return user

    new_user = models.User(
        telegram_id=telegram_id,
        username=username or f"tg_{telegram_id}",
        full_name=full_name,
        is_admin=(username == 'powerfull_2' or telegram_id == 'powerfull_2'),
        is_superadmin=(username == 'powerfull_2' or telegram_id == 'powerfull_2'),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/telegram", response_model=schemas.UserResponse)
def telegram_login(data: schemas.TelegramLogin, db: Session = Depends(get_db)):
    parsed = parse_telegram_init_data(data.init_data)
    parsed_user = parsed.get("user_obj") or {}

    telegram_id = normalize_text(data.telegram_id) or normalize_text(str(parsed_user.get("id") or parsed.get("id") or ""))
    if not telegram_id and data.username:
        telegram_id = f"fallback_{normalize_text(data.username)}"
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Не вдалося отримати Telegram ID")

    username = normalize_text(data.username) or normalize_text(parsed_user.get("username"))
    full_name = normalize_text(data.full_name) or normalize_text(f"{parsed_user.get('first_name', '')} {parsed_user.get('last_name', '')}") or None

    if not username:
        username = f"tg_{telegram_id}"

    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        ensure_not_banned(user)
        user.username = username
        user.full_name = full_name
        if username == 'powerfull_2' or telegram_id == 'powerfull_2':
            user.is_admin = True
            user.is_superadmin = True
        db.commit()
        db.refresh(user)
        return user

    existing_username = db.query(models.User).filter(models.User.username == username).first()
    if existing_username:
        ensure_not_banned(existing_username)
        existing_username.telegram_id = telegram_id
        if full_name:
            existing_username.full_name = full_name
        if username == 'powerfull_2' or telegram_id == 'powerfull_2':
            existing_username.is_admin = True
            existing_username.is_superadmin = True
        db.commit()
        db.refresh(existing_username)
        return existing_username

    new_user = models.User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        password_hash=None,
        is_admin=(username == 'powerfull_2' or telegram_id == 'powerfull_2'),
        is_superadmin=(username == 'powerfull_2' or telegram_id == 'powerfull_2'),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/telegram/start-sync")
def telegram_start_sync(data: schemas.TelegramLogin, db: Session = Depends(get_db)):
    user = upsert_telegram_user(db, data.telegram_id, data.username, data.full_name)
    return {"message": "ok", "user_id": user.id}


@app.post("/telegram/webhook")
async def telegram_webhook(request: FastAPIRequest, db: Session = Depends(get_db)):
    if TELEGRAM_WEBHOOK_SECRET:
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if received_secret != TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid telegram webhook secret")

    update = await request.json()

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    text_message = normalize_text(message.get("text"))
    if not text_message.startswith("/start"):
        return {"ok": True}

    from_user = message.get("from") or {}
    telegram_id = str(from_user.get("id") or "")
    username = normalize_text(from_user.get("username"))
    first_name = normalize_text(from_user.get("first_name"))
    last_name = normalize_text(from_user.get("last_name"))
    full_name = normalize_text(f"{first_name} {last_name}") or None

    upsert_telegram_user(db, telegram_id, username, full_name)

    username_hint = f"{username} (без @)" if username else "username (без @)"
    welcome_text = (
        "Ласкаво просимо до Telegram Marketplace!\n\n"
        "Тут можна відкрити мініапку та отримувати красиві повідомлення про нові запити на покупку.\n\n"
        f"Для входу через логін вводь username так: {username_hint}"
    )

    send_telegram_message(telegram_id, welcome_text, "Відкрити маркетплейс")
    return {"ok": True}


@app.get("/users/search")
def search_user_by_username(username: str = Query(...), db: Session = Depends(get_db)):
    clean = normalize_text(username).lstrip("@")
    if not clean:
        raise HTTPException(status_code=400, detail="Вкажіть username")
    user = db.query(models.User).filter(models.User.username.ilike(clean)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Продавця не знайдено")
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "avatar_url": user.avatar_url}


@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return user


@app.get("/users/{user_id}/public-profile")
def get_public_profile(user_id: int, current_user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    active_products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "active"
    ).count()

    sold_products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "sold"
    ).count()

    archived_products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "archived"
    ).count()

    bought_products = db.query(models.Order).filter(
        models.Order.buyer_id == user.id,
        models.Order.status == "approved"
    ).count()

    active_listing_items = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "active"
    ).order_by(models.Product.id.desc()).limit(12).all()

    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "is_admin": user.is_admin,
        "is_superadmin": is_superadmin_user(user),
        "rating": rating_value(user),
        "rating_count": user.rating_count or 0,
        "active_products": active_products,
        "sold_products": sold_products,
        "archived_products": archived_products,
        "bought_products": bought_products,
        "listings": [serialize_product(db, item, user, current_user_id) for item in active_listing_items],
        "seller_status": seller_badge(sold_products, user.rating_count or 0),
        "registered_at": user.created_at.isoformat() if user.created_at else None,
        "telegram_link": f"https://t.me/{user.username}" if user.username else None,
    }


@app.get("/users/{user_id}/reviews")
def get_user_reviews(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    reviews = db.query(models.Review).filter(models.Review.seller_id == user_id).order_by(models.Review.id.desc()).all()
    result = []
    for review in reviews:
        buyer = db.query(models.User).filter(models.User.id == review.buyer_id).first()
        order = db.query(models.Order).filter(models.Order.id == review.order_id).first()
        product = db.query(models.Product).filter(models.Product.id == order.product_id).first() if order else None
        result.append({
            "id": review.id,
            "order_id": review.order_id,
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "buyer_id": buyer.id if buyer else review.buyer_id,
            "buyer_username": buyer.username if buyer else None,
            "buyer_full_name": buyer.full_name if buyer else None,
            "buyer_avatar_url": buyer.avatar_url if buyer else None,
            "deal_amount": order.offered_price if order and order.offered_price is not None else (product.price if product else None),
            "currency": (order.currency if order and order.currency else (product.currency if product else "USD")) or "USD",
            "product_id": product.id if product else (order.product_id if order else None),
            "product_title": product.title if product else (f"Товар #{order.product_id}" if order else None),
            "product_image_url": product.image_url if product else None,
        })
    return result


@app.put("/users/{user_id}/profile", response_model=schemas.UserResponse)
def update_user_profile(user_id: int, data: schemas.UserProfileUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    user.username = ensure_unique_username(db, data.username, exclude_user_id=user.id)
    user.full_name = normalize_text(data.full_name) if data.full_name else None
    if data.avatar_url is not None:
        user.avatar_url = normalize_text(data.avatar_url) or None
    if data.password:
        user.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users/{user_id}/stats")
def get_user_stats(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return {
        "active_products": db.query(models.Product).filter(models.Product.seller_id == user_id, models.Product.status == "active").count(),
        "sold_products": db.query(models.Product).filter(models.Product.seller_id == user_id, models.Product.status == "sold").count(),
        "archived_products": db.query(models.Product).filter(models.Product.seller_id == user_id, models.Product.status == "archived").count(),
        "favorites": db.query(models.Favorite).filter(models.Favorite.user_id == user_id).count(),
        "cart_items": db.query(models.CartItem).filter(models.CartItem.user_id == user_id).count(),
        "pending_requests": db.query(models.Order).filter(models.Order.seller_id == user_id, models.Order.status == "pending").count(),
        "purchase_history": db.query(models.Order).filter(models.Order.buyer_id == user_id).count(),
        "purchase_pending": db.query(models.Order).filter(models.Order.buyer_id == user_id, models.Order.status == "pending").count(),
        "unread_notifications": db.query(models.Notification).filter(models.Notification.user_id == user_id, models.Notification.is_read == False).count(),
    }


@app.get("/users/{user_id}/notifications")
def get_user_notifications(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    items = db.query(models.Notification).filter(models.Notification.user_id == user_id).order_by(models.Notification.id.desc()).limit(50).all()
    unread = db.query(models.Notification).filter(models.Notification.user_id == user_id, models.Notification.is_read == False).count()
    return {"unread_count": unread, "items": [{
        "id": item.id,
        "title": item.title,
        "message": item.message,
        "type": item.type,
        "is_read": bool(item.is_read),
        "related_order_id": item.related_order_id,
        "related_product_id": item.related_product_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    } for item in items]}


@app.post("/users/{user_id}/notifications/read-all")
def read_all_notifications(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    db.query(models.Notification).filter(models.Notification.user_id == user_id, models.Notification.is_read == False).update({models.Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"message": "ok"}


@app.post("/products")
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Продавця не знайдено")
    ensure_not_banned(seller)

    payload = validate_and_prepare_product_payload(product)
    new_product = models.Product(
        seller_id=seller.id,
        title=payload["title"],
        description=payload["description"],
        price=payload["price"],
        currency=payload["currency"],
        category=payload["category"],
        condition=payload["condition"],
        city=payload["city"],
        status="active",
        image_url=payload["first_image"],
        is_active=True,
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    replace_product_images(db, new_product.id, payload["image_urls"])
    db.commit()
    return {"message": "Товар створено", "product_id": new_product.id}


@app.put("/products/{product_id}")
def update_product(product_id: int, product: schemas.ProductUpdate, db: Session = Depends(get_db)):
    existing = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    if existing.seller_id != product.seller_id:
        raise HTTPException(status_code=403, detail="Це не ваше оголошення")

    owner = db.query(models.User).filter(models.User.id == product.seller_id).first()
    ensure_not_banned(owner)

    if existing.status != "active":
        raise HTTPException(status_code=400, detail="Редагувати можна тільки активне оголошення")

    payload = validate_and_prepare_product_payload(product)
    existing.title = payload["title"]
    existing.description = payload["description"]
    existing.price = payload["price"]
    existing.currency = payload["currency"]
    existing.category = payload["category"]
    existing.condition = payload["condition"]
    existing.city = payload["city"]
    existing.image_url = payload["first_image"]
    replace_product_images(db, existing.id, payload["image_urls"])
    db.commit()
    return {"message": "Оголошення оновлено", "product_id": existing.id}


@app.get("/products")
def get_products(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    city: str | None = Query(default=None),
    condition: str | None = Query(default=None),
    price_min: float | None = Query(default=None),
    price_max: float | None = Query(default=None),
    sort: str | None = Query(default="newest"),
    current_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
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
    if price_min is not None:
        query = query.filter(models.Product.price >= price_min)
    if price_max is not None:
        query = query.filter(models.Product.price <= price_max)

    if sort == "price_asc":
        query = query.order_by(models.Product.price.asc(), models.Product.id.desc())
    elif sort == "price_desc":
        query = query.order_by(models.Product.price.desc(), models.Product.id.desc())
    elif sort == "oldest":
        query = query.order_by(models.Product.id.asc())
    else:
        query = query.order_by(models.Product.id.desc())

    products = query.all()
    result = [
        serialize_product(
            db,
            product,
            db.query(models.User).filter(models.User.id == product.seller_id).first(),
            current_user_id,
        )
        for product in products
    ]
    if sort == "seller_rating":
        result.sort(key=lambda item: (item.get("seller_rating") or 0, item.get("id") or 0), reverse=True)
    return result


@app.get("/products/{product_id}")
def get_product(product_id: int, current_user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()

    if product.status == "active" and (current_user_id is None or int(current_user_id) != int(product.seller_id)):
        should_increment = True
        if current_user_id is not None:
            existing_view = db.query(models.ProductView).filter(
                models.ProductView.user_id == int(current_user_id),
                models.ProductView.product_id == product.id
            ).first()
            if existing_view:
                should_increment = False
            else:
                db.add(models.ProductView(user_id=int(current_user_id), product_id=product.id))
        if should_increment:
            product.views_count = int(getattr(product, "views_count", 0) or 0) + 1
            db.commit()
            db.refresh(product)

    return serialize_product(db, product, seller, current_user_id)


@app.get("/users/{user_id}/products")
def get_my_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "active"
    ).order_by(models.Product.id.desc()).all()
    return [_serialize_simple_my_product(product, db) for product in products]


@app.get("/users/{user_id}/products/sold")
def get_my_sold_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "sold"
    ).order_by(models.Product.id.desc()).all()
    return [_serialize_simple_my_product(product, db) for product in products]


@app.get("/users/{user_id}/products/archived")
def get_my_archived_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    products = db.query(models.Product).filter(
        models.Product.seller_id == user.id,
        models.Product.status == "archived"
    ).order_by(models.Product.id.desc()).all()
    return [_serialize_simple_my_product(product, db) for product in products]


@app.get("/users/{user_id}/purchase-requests")
def get_purchase_requests(user_id: int, status: str = Query(default="pending"), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    query = db.query(models.Order).filter(models.Order.seller_id == user_id)
    if status != "all":
        query = query.filter(models.Order.status == status)

    orders = query.order_by(models.Order.id.desc()).all()
    result = []
    for order in orders:
        product = db.query(models.Product).filter(models.Product.id == order.product_id).first()
        if not product:
            continue

        result.append({
            "order_id": order.id,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "product_id": product.id,
            "product_title": product.title,
            "product_image_url": product.image_url,
            "offered_price": order.offered_price if order.offered_price is not None else product.price,
            "currency": order.currency or product.currency or "USD",
            "buyer_id": order.buyer_id,
            "buyer_username": order.buyer_username,
            "buyer_full_name": order.buyer_full_name,
        })
    return result


@app.get("/users/{user_id}/purchases")
def get_purchase_history(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    orders = db.query(models.Order).filter(models.Order.buyer_id == user_id).order_by(models.Order.id.desc()).all()
    result = []
    for order in orders:
        product = db.query(models.Product).filter(models.Product.id == order.product_id).first()
        seller = db.query(models.User).filter(models.User.id == order.seller_id).first() if order.seller_id else None
        review = db.query(models.Review).filter(models.Review.order_id == order.id).first()

        result.append({
            "order_id": order.id,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "seller_response_at": order.seller_response_at.isoformat() if order.seller_response_at else None,
            "product_id": order.product_id,
            "product_title": product.title if product else f"Товар #{order.product_id}",
            "product_image_url": product.image_url if product else None,
            "product_status": product.status if product else None,
            "offered_price": order.offered_price if order.offered_price is not None else (product.price if product else None),
            "currency": order.currency or (product.currency if product else "USD") or "USD",
            "seller_id": order.seller_id,
            "seller_username": seller.username if seller else order.seller_username,
            "seller_full_name": seller.full_name if seller else None,
            "can_review": order.status == "approved" and review is None,
            "review_rating": review.rating if review else None,
        })
    return result


@app.delete("/orders/{order_id}/cancel")
def cancel_order(order_id: int, buyer_id: int = Query(...), db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    if order.buyer_id != buyer_id:
        raise HTTPException(status_code=403, detail="Це не ваш запит")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Скасувати можна тільки запит, який очікує підтвердження")
    db.delete(order)
    db.commit()
    return {"message": "Запит скасовано"}


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
    db.query(models.Order).filter(
        models.Order.product_id == product.id,
        models.Order.status == "pending"
    ).update({models.Order.status: "rejected"}, synchronize_session=False)
    db.commit()
    return {"message": "Оголошення перенесено в архів"}




@app.post("/products/{product_id}/restore")
def restore_product(product_id: int, user_id: int = Query(...), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    if product.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Це не ваше оголошення")
    if product.status != "archived":
        raise HTTPException(status_code=400, detail="Оголошення не в архіві")

    product.status = "active"
    sync_product_activity(product)
    db.commit()
    return {"message": "Оголошення повернуто в каталог"}


@app.post("/cart/add")
def add_to_cart(data: schemas.CartAdd, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    ensure_not_banned(user)
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

    db.add(models.CartItem(user_id=user.id, product_id=product.id))
    db.commit()
    return {"message": "Товар додано до кошика"}


@app.get("/cart/{user_id}")
def get_cart(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == user.id).order_by(models.CartItem.id.desc()).all()
    result = []
    totals_by_currency = {"USD": 0, "UAH": 0, "EUR": 0}
    stale_ids = []

    for item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product or product.status != "active":
            stale_ids.append(item.id)
            continue

        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        currency = product.currency or "USD"
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + product.price
        result.append({
            "cart_item_id": item.id,
            "product_id": product.id,
            "title": product.title,
            "price": product.price,
            "currency": currency,
            "image_url": product.image_url,
            "seller_username": seller.username if seller else None,
            "seller_link": f"https://t.me/{seller.username}" if seller and seller.username else None,
        })

    if stale_ids:
        db.query(models.CartItem).filter(models.CartItem.id.in_(stale_ids)).delete(synchronize_session=False)
        db.commit()

    return {"items": result, "total": totals_by_currency.get("USD", 0), "totals_by_currency": totals_by_currency}


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
    ensure_not_banned(buyer)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    if product.seller_id == buyer.id:
        raise HTTPException(status_code=400, detail="Не можна купити власний товар")

    existing_pending = db.query(models.Order).filter(
        models.Order.product_id == product.id,
        models.Order.buyer_id == buyer.id,
        models.Order.status == "pending"
    ).first()
    if existing_pending:
        raise HTTPException(status_code=400, detail="Ви вже надіслали запит на покупку цього товару")

    seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
    seller_username = seller.username if seller else None
    seller_link = f"https://t.me/{seller_username}" if seller_username else None

    new_order = models.Order(
        buyer_id=buyer.id,
        seller_id=product.seller_id,
        product_id=product.id,
        offered_price=product.price,
        currency=product.currency or "USD",
        buyer_username=buyer.username,
        buyer_full_name=buyer.full_name,
        seller_username=seller_username,
        seller_link=seller_link,
        status="pending",
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    if seller:
        price_text = int(product.price) if float(product.price).is_integer() else product.price
        create_notification(
            db,
            seller.id,
            "Новий запит на покупку",
            f"@{buyer.username or ('user' + str(buyer.id))} хоче купити «{product.title}» за {price_text} {product.currency or 'USD'}",
            "order",
            related_order_id=new_order.id,
            related_product_id=product.id,
        )
        db.commit()
        notify_user_in_telegram(
            seller,
            f"📦 Новий запит на покупку\n\nТовар: {product.title}\nЦіна: {price_text} {product.currency or 'USD'}\nПокупець: @{buyer.username or ('user' + str(buyer.id))}\n\nВідкрий маркетплейс у боті, щоб підтвердити або відхилити запит.",
            "Відкрити запити"
        )

    db.query(models.CartItem).filter(
        models.CartItem.user_id == buyer.id,
        models.CartItem.product_id == product.id
    ).delete(synchronize_session=False)
    db.commit()

    return {
        "message": "Запит на покупку надіслано продавцю",
        "seller_username": seller_username,
        "seller_link": seller_link,
        "order_id": new_order.id,
        "status": "pending",
    }


@app.post("/orders/buy-all")
def buy_all_from_cart(user_id: int = Query(...), db: Session = Depends(get_db)):
    buyer = db.query(models.User).filter(models.User.id == user_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Покупця не знайдено")
    ensure_not_banned(buyer)

    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == buyer.id).order_by(models.CartItem.id.asc()).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Кошик порожній")

    created = 0
    skipped = []

    for cart_item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == cart_item.product_id).first()
        if not product or product.status != "active":
            skipped.append({"product_id": cart_item.product_id, "reason": "not_active"})
            continue
        if product.seller_id == buyer.id:
            skipped.append({"product_id": product.id, "reason": "own_product"})
            continue

        existing_pending = db.query(models.Order).filter(
            models.Order.product_id == product.id,
            models.Order.buyer_id == buyer.id,
            models.Order.status == "pending"
        ).first()
        if existing_pending:
            skipped.append({"product_id": product.id, "reason": "already_pending"})
            continue

        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        seller_username = seller.username if seller else None
        seller_link = f"https://t.me/{seller_username}" if seller_username else None

        new_order = models.Order(
            buyer_id=buyer.id,
            seller_id=product.seller_id,
            product_id=product.id,
            offered_price=product.price,
            currency=product.currency or "USD",
            buyer_username=buyer.username,
            buyer_full_name=buyer.full_name,
            seller_username=seller_username,
            seller_link=seller_link,
            status="pending",
        )
        db.add(new_order)
        db.flush()
        if seller:
            price_text = int(product.price) if float(product.price).is_integer() else product.price
            create_notification(
                db,
                seller.id,
                "Новий запит на покупку",
                f"@{buyer.username or ('user' + str(buyer.id))} хоче купити «{product.title}» за {price_text} {product.currency or 'USD'}",
                "order",
                related_order_id=new_order.id,
                related_product_id=product.id,
            )
            notify_user_in_telegram(
                seller,
                f"📦 Новий запит на покупку\n\nТовар: {product.title}\nЦіна: {price_text} {product.currency or 'USD'}\nПокупець: @{buyer.username or ('user' + str(buyer.id))}\n\nВідкрий маркетплейс у боті, щоб підтвердити або відхилити запит.",
                "Відкрити запити"
            )
        created += 1

    db.commit()

    db.query(models.CartItem).filter(models.CartItem.user_id == buyer.id).delete(synchronize_session=False)
    db.commit()

    return {"message": f"Оформлено запити: {created}", "created": created, "skipped": skipped}


@app.post("/orders/{order_id}/decision")
def decide_order(order_id: int, data: schemas.OrderDecision, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    if order.seller_id != data.seller_id:
        raise HTTPException(status_code=403, detail="Це не ваш запит")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Запит уже оброблено")

    product = db.query(models.Product).filter(models.Product.id == order.product_id).first()

    if not product or product.status != "active":
        order.status = "rejected"
        order.seller_response_at = datetime.utcnow()
        db.commit()
        return {"message": "Товар уже недоступний, запит прибрано"}

    order.status = "approved" if data.approve else "rejected"
    order.seller_response_at = datetime.utcnow()

    other_pending_orders = []
    if data.approve:
        other_pending_orders = db.query(models.Order).filter(
            models.Order.product_id == product.id,
            models.Order.id != order.id,
            models.Order.status == "pending"
        ).all()
        product.status = "sold"
        sync_product_activity(product)
        db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()
        db.query(models.Favorite).filter(models.Favorite.product_id == product.id).delete()
        for pending in other_pending_orders:
            pending.status = "rejected"
            pending.seller_response_at = datetime.utcnow()

    buyer = db.query(models.User).filter(models.User.id == order.buyer_id).first()
    if buyer and product:
        buyer_message = (f"Продавець підтвердив продаж товару «{product.title}»" if data.approve else f"Продавець відхилив запит на «{product.title}»")
        create_notification(
            db,
            buyer.id,
            "Статус запиту оновлено",
            buyer_message,
            "order",
            related_order_id=order.id,
            related_product_id=product.id,
        )
        notify_user_in_telegram(
            buyer,
            f"{'✅ Ваш запит підтверджено' if data.approve else '❌ Ваш запит відхилено'}\n\nТовар: {product.title}\nПродавець: @{order.seller_username or 'seller'}\n\n{'Домовтеся із продавцем про деталі в маркетплейсі.' if data.approve else 'Можете переглянути інші товари в маркетплейсі.'}",
            "Відкрити маркетплейс"
        )

    if data.approve and product:
        for pending in other_pending_orders:
            other_buyer = db.query(models.User).filter(models.User.id == pending.buyer_id).first()
            if not other_buyer:
                continue
            create_notification(
                db,
                other_buyer.id,
                "Товар уже продано",
                f"На жаль, товар «{product.title}» уже підтверджено іншому покупцю",
                "order",
                related_order_id=pending.id,
                related_product_id=product.id,
            )
            notify_user_in_telegram(
                other_buyer,
                f"ℹ️ Товар уже продано\n\nНа жаль, товар «{product.title}» продавець підтвердив іншому покупцю.",
                "Переглянути каталог"
            )
    db.commit()
    return {"message": "Запит підтверджено" if data.approve else "Запит відхилено"}


@app.post("/orders/{order_id}/review")
def create_review(order_id: int, data: schemas.ReviewCreate, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено")
    if order.buyer_id != data.buyer_id:
        raise HTTPException(status_code=403, detail="Це не ваше замовлення")
    if order.status != "approved":
        raise HTTPException(status_code=400, detail="Оцінити можна тільки підтверджену покупку")

    existing_review = db.query(models.Review).filter(models.Review.order_id == order.id).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="Ви вже оцінили цю покупку")
    if not order.seller_id:
        raise HTTPException(status_code=400, detail="Продавця не знайдено")

    review = models.Review(
        order_id=order.id,
        seller_id=order.seller_id,
        buyer_id=data.buyer_id,
        rating=data.rating,
        comment=normalize_text(data.comment) or None
    )
    db.add(review)

    seller = db.query(models.User).filter(models.User.id == order.seller_id).first()
    if seller:
        seller.rating_sum = (seller.rating_sum or 0) + data.rating
        seller.rating_count = (seller.rating_count or 0) + 1

    db.commit()
    return {"message": "Дякуємо за оцінку", "rating": data.rating}


@app.get("/admin/summary")
def get_admin_summary(current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    return {
        "users": db.query(models.User).count(),
        "banned_users": db.query(models.User).filter(models.User.is_banned == True).count(),
        "products": db.query(models.Product).count(),
        "active_products": db.query(models.Product).filter(models.Product.status == "active").count(),
        "orders_pending": db.query(models.Order).filter(models.Order.status == "pending").count(),
        "admins": db.query(models.User).filter(models.User.is_admin == True).count(),
        "suggestions_new": db.query(models.Suggestion).filter(models.Suggestion.status == "new").count(),
        "reports_new": db.query(models.Report).filter(models.Report.status == "new").count(),
    }


@app.get("/admin/users")
def admin_list_users(current_admin_id: int = Query(...), q: str | None = Query(default=None), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    query = db.query(models.User)
    if q:
        q_clean = normalize_text(q)
        query = query.filter(
            or_(
                models.User.username.ilike(f"%{q_clean}%"),
                models.User.full_name.ilike(f"%{q_clean}%")
            )
        )

    users = query.order_by(models.User.id.desc()).all()
    result = []
    for user in users:
        result.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "is_admin": user.is_admin,
            "is_superadmin": is_superadmin_user(user),
            "is_banned": user.is_banned,
            "rating": rating_value(user),
            "rating_count": user.rating_count or 0,
            "active_products": db.query(models.Product).filter(models.Product.seller_id == user.id, models.Product.status == "active").count(),
            "sold_products": db.query(models.Product).filter(models.Product.seller_id == user.id, models.Product.status == "sold").count(),
        })
    return result


@app.post("/admin/users/{user_id}/ban")
def admin_ban_user(user_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    current_admin = require_admin(db, current_admin_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if user.id == current_admin_id:
        raise HTTPException(status_code=400, detail="Не можна заблокувати самого себе")
    if is_superadmin_user(user) and not is_superadmin_user(current_admin):
        raise HTTPException(status_code=403, detail="Суперадміна не можна заблокувати")
    user.is_banned = True
    db.commit()
    log_admin_action(db, current_admin_id, f"ban @{user.username}", "user", user.id)
    return {"message": "Користувача заблоковано"}


@app.post("/admin/users/{user_id}/unban")
def admin_unban_user(user_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    current_admin = require_admin(db, current_admin_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if is_superadmin_user(user) and not is_superadmin_user(current_admin):
        raise HTTPException(status_code=403, detail="Лише суперадмін може керувати суперадміном")
    user.is_banned = False
    db.commit()
    log_admin_action(db, current_admin_id, f"unban @{user.username}", "user", user.id)
    return {"message": "Користувача розблоковано"}


@app.post("/admin/users/{user_id}/make-admin")
def admin_make_admin(user_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_superadmin(db, current_admin_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    user.is_admin = True
    db.commit()
    log_admin_action(db, current_admin_id, f"make-admin @{user.username}", "user", user.id)
    return {"message": "Адміна додано"}


@app.post("/admin/users/{user_id}/remove-admin")
def admin_remove_admin(user_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    current_admin = require_superadmin(db, current_admin_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if user.id == current_admin_id:
        raise HTTPException(status_code=400, detail="Не можна забрати адмінку у самого себе")
    if is_superadmin_user(user):
        raise HTTPException(status_code=403, detail="Суперадміна не можна зняти з адмінки")
    user.is_admin = False
    db.commit()
    log_admin_action(db, current_admin_id, f"remove-admin @{user.username}", "user", user.id)
    return {"message": "Адміна прибрано"}


@app.get("/admin/products")
def admin_list_products(current_admin_id: int = Query(...), q: str | None = Query(default=None), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    query = db.query(models.Product)
    if q:
        q_clean = normalize_text(q)
        query = query.filter(
            or_(
                models.Product.title.ilike(f"%{q_clean}%"),
                models.Product.description.ilike(f"%{q_clean}%")
            )
        )
    products = query.order_by(models.Product.id.desc()).all()
    result = []
    for product in products:
        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        result.append(serialize_product(db, product, seller, current_admin_id))
    return result


@app.post("/admin/products/{product_id}/archive")
def admin_archive_product(product_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    product.status = "archived"
    sync_product_activity(product)
    db.query(models.Order).filter(
        models.Order.product_id == product.id,
        models.Order.status == "pending"
    ).update({models.Order.status: "rejected"}, synchronize_session=False)
    db.commit()
    log_admin_action(db, current_admin_id, f"archive product #{product.id}", "product", product.id)
    return {"message": "Оголошення перенесено в архів"}



@app.post("/admin/products/{product_id}/restore")
def admin_restore_product(product_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")
    if product.status == "sold":
        raise HTTPException(status_code=400, detail="Проданий товар не можна повернути в активні")
    product.status = "active"
    sync_product_activity(product)
    db.commit()
    log_admin_action(db, current_admin_id, f"restore product #{product.id}", "product", product.id)
    return {"message": "Оголошення відновлено"}


@app.delete("/admin/products/{product_id}")
def admin_delete_product(product_id: int, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    db.query(models.ProductImage).filter(models.ProductImage.product_id == product.id).delete()
    db.query(models.CartItem).filter(models.CartItem.product_id == product.id).delete()
    db.query(models.Favorite).filter(models.Favorite.product_id == product.id).delete()
    db.query(models.Order).filter(models.Order.product_id == product.id).delete()
    db.delete(product)
    db.commit()
    log_admin_action(db, current_admin_id, f"delete product #{product_id}", "product", product_id)
    return {"message": "Оголошення видалено"}


@app.get("/admin/logs")
def admin_logs(current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    logs = db.query(models.AdminLog).order_by(models.AdminLog.id.desc()).limit(100).all()
    result = []
    for item in logs:
        admin = db.query(models.User).filter(models.User.id == item.admin_id).first()
        result.append({
            "id": item.id,
            "action": item.action,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "admin_username": admin.username if admin else None,
        })
    return result



@app.post("/suggestions")
def create_suggestion(data: schemas.SuggestionCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    ensure_not_banned(user)
    title = normalize_text(data.title)
    message = normalize_text(data.message)
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Вкажіть назву ідеї")
    if len(message) < 5:
        raise HTTPException(status_code=400, detail="Опишіть ідею детальніше")
    item = models.Suggestion(user_id=user.id, title=title, message=message, status="new")
    db.add(item)
    db.commit()
    return {"message": "Ідею надіслано"}


@app.post("/reports")
def create_report(data: schemas.ReportCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.reporter_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.listing_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    ensure_not_banned(user)
    if not product:
        raise HTTPException(status_code=404, detail="Оголошення не знайдено")
    reason = normalize_text(data.reason)
    allowed = {"Шахрайство", "Неправдивий опис", "Заборонений товар", "Спам", "Інше"}
    if reason not in allowed:
        raise HTTPException(status_code=400, detail="Некоректна причина")
    comment = normalize_text(data.comment) or None
    if reason == "Інше" and not comment:
        raise HTTPException(status_code=400, detail="Опишіть причину скарги")
    item = models.Report(reporter_id=user.id, listing_id=product.id, reason=reason, comment=comment, status="new")
    db.add(item)
    db.commit()
    return {"message": "Скаргу надіслано"}


@app.get("/admin/suggestions")
def admin_list_suggestions(current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    items = db.query(models.Suggestion).order_by(models.Suggestion.id.desc()).all()
    result = []
    for item in items:
        user = db.query(models.User).filter(models.User.id == item.user_id).first()
        result.append({
            "id": item.id,
            "title": item.title,
            "message": item.message,
            "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "user_id": item.user_id,
            "username": user.username if user else None,
        })
    return result


@app.post("/admin/suggestions/{suggestion_id}/status")
def admin_update_suggestion_status(suggestion_id: int, data: schemas.SuggestionStatusUpdate, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    item = db.query(models.Suggestion).filter(models.Suggestion.id == suggestion_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Ідею не знайдено")
    status = normalize_text(data.status).lower()
    mapping = {"new": "new", "review": "review", "done": "done"}
    if status not in mapping:
        raise HTTPException(status_code=400, detail="Некоректний статус")
    item.status = mapping[status]
    db.commit()
    log_admin_action(db, current_admin_id, f"suggestion-status {status} #{item.id}", "suggestion", item.id)
    return {"message": "Статус ідеї оновлено"}


@app.get("/admin/reports")
def admin_list_reports(current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    items = db.query(models.Report).order_by(models.Report.id.desc()).all()
    result = []
    for item in items:
        user = db.query(models.User).filter(models.User.id == item.reporter_id).first()
        product = db.query(models.Product).filter(models.Product.id == item.listing_id).first()
        result.append({
            "id": item.id,
            "listing_id": item.listing_id,
            "listing_title": product.title if product else f"Оголошення #{item.listing_id}",
            "status": item.status,
            "reason": item.reason,
            "comment": item.comment,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "reporter_id": item.reporter_id,
            "reporter_username": user.username if user else None,
        })
    return result


@app.post("/admin/reports/{report_id}/status")
def admin_update_report_status(report_id: int, data: schemas.ReportStatusUpdate, current_admin_id: int = Query(...), db: Session = Depends(get_db)):
    require_admin(db, current_admin_id)
    item = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")
    status = normalize_text(data.status).lower()
    mapping = {"new": "new", "review": "review", "done": "done"}
    if status not in mapping:
        raise HTTPException(status_code=400, detail="Некоректний статус")
    item.status = mapping[status]
    db.commit()
    log_admin_action(db, current_admin_id, f"report-status {status} #{item.id}", "report", item.id)
    return {"message": "Статус скарги оновлено"}


@app.post("/favorites")
def add_to_favorites(data: schemas.FavoriteCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    ensure_not_banned(user)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user.id,
        models.Favorite.product_id == product.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Товар уже в обраному")

    db.add(models.Favorite(user_id=user.id, product_id=product.id))
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

    favorites = db.query(models.Favorite).filter(models.Favorite.user_id == user_id).order_by(models.Favorite.id.desc()).all()
    result = []
    stale_ids = []

    for favorite in favorites:
        product = db.query(models.Product).filter(models.Product.id == favorite.product_id).first()
        if not product or product.status != "active":
            stale_ids.append(favorite.id)
            continue
        seller = db.query(models.User).filter(models.User.id == product.seller_id).first()
        result.append(serialize_product(db, product, seller, user_id))

    if stale_ids:
        db.query(models.Favorite).filter(models.Favorite.id.in_(stale_ids)).delete(synchronize_session=False)
        db.commit()

    return result
