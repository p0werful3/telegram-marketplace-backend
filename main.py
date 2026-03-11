from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, get_db
import models
import schemas

app = FastAPI(title="Telegram Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Telegram Marketplace API працює"}


@app.post("/users/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.telegram_id == user.telegram_id).first()

    if existing_user:
        if user.username:
            existing_user.username = user.username
        existing_user.full_name = user.full_name
        db.commit()
        db.refresh(existing_user)
        return existing_user

    new_user = models.User(
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.get("/users/{telegram_id}", response_model=schemas.UserResponse)
def get_user(telegram_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return user


@app.post("/products")
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    seller = db.query(models.User).filter(models.User.telegram_id == product.seller_telegram_id).first()

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

    return {
        "message": "Товар створено",
        "product_id": new_product.id
    }


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
            "seller_telegram_link": f"https://t.me/{seller.username}" if seller and seller.username else None,
            "is_owner": False
        })

    return result


@app.get("/users/{telegram_id}/products")
def get_my_products(telegram_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()

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
def delete_product(
    product_id: int,
    telegram_id: str = Query(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    if product.seller_id != user.id:
        raise HTTPException(status_code=403, detail="Це не ваше оголошення")

    product.is_active = False
    db.commit()

    return {"message": "Оголошення видалено"}


@app.post("/cart/add")
def add_to_cart(data: schemas.CartAdd, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.telegram_id == data.user_telegram_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    cart_item = models.CartItem(
        user_id=user.id,
        product_id=product.id
    )
    db.add(cart_item)
    db.commit()

    return {"message": "Товар додано до кошика"}


@app.get("/cart/{telegram_id}")
def get_cart(telegram_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == user.id).all()

    result = []
    total = 0

    for item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id, models.Product.is_active == True).first()
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

    return {
        "items": result,
        "total": total
    }


@app.post("/orders/buy")
def buy_product(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    buyer = db.query(models.User).filter(models.User.telegram_id == data.buyer_telegram_id).first()
    product = db.query(models.Product).filter(models.Product.id == data.product_id, models.Product.is_active == True).first()

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
