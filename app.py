from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp
import qrcode
import base64
from io import BytesIO
from datetime import timedelta
from functools import wraps
from flask import abort
import os


app = Flask(__name__)
app.config["SECRET_KEY"] = "4f9b8e7d6c5a3b2f1e0d9c8b7a6f5e4d3c2b1a0987654321ff8e7d6c5b4a3f"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=7)
app.config["ADMIN_EMAIL"] = os.environ.get("ADMIN_EMAIL", "admin@shop.com")
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "Admin12345!")


db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    twofa_enabled = db.Column(db.Boolean, default=False)
    twofa_secret = db.Column(db.String(64), nullable=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100), nullable=False, default="Букети")
    is_bestseller = db.Column(db.Boolean, default=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="created")  # created/paid/shipped...
    total = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(250), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    has_card = db.Column(db.Boolean, default=False)
    card_message = db.Column(db.Text)

    user = db.relationship("User", backref="orders")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    qty = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    line_total = db.Column(db.Float, nullable=False)

    order = db.relationship("Order", backref="items")
    product = db.relationship("Product")

   
class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    order = db.relationship("Order", backref="status_history")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def get_cart() -> dict:
    # cart format: {"product_id_as_str": qty_int}
    return session.get("cart", {})

def save_cart(cart: dict):
    session["cart"] = cart
    session.modified = True

def cart_count() -> int:
    return sum(get_cart().values())

def generate_qr_data_uri(otpauth_url: str) -> str:
    img = qrcode.make(otpauth_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def init_db_with_products():
    if Product.query.count() == 0:
        demo = [
            Product(name="Класически червени рози", description="Букет от 11 червени рози – символ на любовта.", price=29.90,
                    category="Рози", image_url="products/red.jpeg", stock=15, is_bestseller=True),
            Product( name="Бели елегантни рози", description="Нежен букет от 9 бели рози.", price=24.90,
                    category="Рози", image_url="products/withe.jpeg",stock=12),
            Product( name="Розов романтичен букет", description="12 розови рози за специален повод.", price=34.90,
                    category="Рози", image_url="products/pink.jpeg", stock=10),
            Product( name="Микс рози Deluxe", description="Червени, бели и розови рози в луксозна аранжировка.",price=59.90,
                    category="Рози", image_url="products/mix.jpeg", stock=8 ),
            Product( name="Пролетни лалета", description="Свежи разноцветни лалета.", price=29.90,
                    category="Лалета", image_url="products/laleta.jpeg",stock=20),
            Product( name="Розови лалета", description="Нежни розови лалета.", price=34.90,
                    category="Лалета", image_url="products/laleta_pink.jpeg",stock=18),
            Product( name="Пастелен букет", description="Комбинация от рози, еустома и гипсофила.", price=59.90,
                    category="Букети", image_url="products/pastel.jpeg", stock=10),
            Product( name="Романтичен микс", description="Червено-розов букет с декоративна зеленина.", price=64.90,
                    category="Букети", image_url="products/romantichen.jpeg",stock=7, is_bestseller=True),
            Product(name="Летен свеж букет", description="Слънчогледи и полски цветя.", price=42.90,
                     category="Букети", image_url="products/leten.jpeg", stock=12),
            Product( name="Луксозен сватбен букет", description="Изискана аранжировка за специални моменти.", price=89.90,
                    category="Букети", image_url="products/svatben.jpeg", stock=5),
            Product(name="Осмомартенска нежност", description="Свежа комбинация от алени гербери и розови рози, допълнени с деликатна хортензия и зелени акценти.", price=45.90,
                     category="8 март", image_url="products/m1.jpeg", stock=13),
            Product( name="Кокетна чантичка", description="Аранжирани сапунени рози в кутия.", price=38.90,
                    category="8 март", image_url="products/m2.jpeg", stock=25),
        ]
        db.session.add_all(demo)
        db.session.commit()

def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/products")
def products():
    category = request.args.get("category")

    if category:
        products = Product.query.filter_by(category=category).all()
    else:
        products = Product.query.all()

    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]

    return render_template(
        "products.html",
        products=products,
        categories=categories,
        selected_category=category
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Попълни имейл и парола.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Този имейл вече е регистриран.")
            return redirect(url_for("register"))

        user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash("Регистрацията е успешна. Влез в акаунта.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Грешен имейл или парола.")
            return redirect(url_for("login"))

        if not user:
            flash("Нямаш акаунт. Регистрирай се.")
            return redirect(url_for("login"))
        
        if user.twofa_enabled:
            session["pre_2fa_user_id"] = user.id
            return redirect(url_for("twofa_verify"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html")

@app.route("/2fa/verify", methods=["GET", "POST"])
def twofa_verify():
    user_id = session.get("pre_2fa_user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = db.session.get(User, int(user_id))
    if not user or not user.twofa_enabled or not user.twofa_secret:
        flash("2FA не е конфигурирана.")
        session.pop("pre_2fa_user_id", None)
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip().replace(" ", "")
        totp = pyotp.TOTP(user.twofa_secret)
        if totp.verify(code, valid_window=1):
            session.pop("pre_2fa_user_id", None)
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Невалиден код. Опитай пак.")

    return render_template("twofa_verify.html")

@app.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def twofa_setup():
    if not current_user.twofa_secret:
        current_user.twofa_secret = pyotp.random_base32()
        db.session.commit()

    issuer = "DidiFlowerShop"
    label = current_user.email
    totp = pyotp.TOTP(current_user.twofa_secret)
    otpauth_url = totp.provisioning_uri(name=label, issuer_name=issuer)
    qr_uri = generate_qr_data_uri(otpauth_url)

    if request.method == "POST":
        code = request.form.get("code", "").strip().replace(" ", "")
        if totp.verify(code, valid_window=1):
            current_user.twofa_enabled = True
            db.session.commit()
            flash("2FA е активирана.")
            return redirect(url_for("dashboard"))
        else:
            flash("Кодът не е валиден. Сканирай QR и въведи текущия код.")

    return render_template("twofa_setup.html", qr_uri=qr_uri, secret=current_user.twofa_secret)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Попълни всички полета.")
            return redirect(url_for("contact"))

        db.session.add(ContactMessage(name=name, email=email, message=message))
        db.session.commit()
        flash("Съобщението е изпратено. Ще се свържем с теб.")
        return redirect(url_for("contact"))

    return render_template("contact.html")

@app.context_processor
def inject_cart_count():
    return {"cart_count": cart_count()}

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped



@app.get("/admin")
@admin_required
def admin_home():
    return redirect(url_for("admin_orders"))

@app.get("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template("admin_orders.html", orders=orders)

@app.get("/admin/orders/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        flash("Няма такава поръчка.")
        return redirect(url_for("admin_orders"))
    return render_template("admin_order_detail.html", order=order)

@app.post("/admin/orders/<int:order_id>/status")
@admin_required
def admin_set_order_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        flash("Няма такава поръчка.")
        return redirect(url_for("admin_orders"))

    new_status = request.form.get("status", "").strip()

    allowed = ["created", "confirmed", "shipping", "shipped", "cancelled"]
    if new_status not in allowed:
        flash("Невалиден статус.")
        return redirect(url_for("admin_order_detail", order_id=order.id))

    order.status = new_status
    db.session.add(OrderStatusHistory(order_id=order.id, status=new_status))
    db.session.commit()

    flash("Статусът е обновен.")
    return redirect(url_for("admin_order_detail", order_id=order.id))

@app.post("/cart/add/<int:product_id>")
def cart_add(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash("Няма такъв продукт.")
        return redirect(url_for("products"))

    cart = get_cart()
    key = str(product_id)
    cart[key] = cart.get(key, 0) + 1
    save_cart(cart)

    flash("Добавено в количката.")
    return redirect(url_for("products"))

@app.get("/cart")
def cart_view():
    cart = get_cart()
    items = []
    total = 0.0

    if cart:
        product_ids = [int(pid) for pid in cart.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        product_map = {p.id: p for p in products}

        for pid_str, qty in cart.items():
            pid = int(pid_str)
            p = product_map.get(pid)
            if not p:
                continue
            line_total = float(p.price) * int(qty)
            total += line_total
            items.append({
                "product": p,
                "qty": int(qty),
                "line_total": line_total
            })

    return render_template("cart.html", items=items, total=total)

@app.post("/cart/update")
def cart_update():
    cart = get_cart()
    # очакваме полета qty_<productId>
    for key in list(cart.keys()):
        form_key = f"qty_{key}"
        if form_key in request.form:
            try:
                qty = int(request.form.get(form_key, "1"))
            except ValueError:
                qty = 1

            if qty <= 0:
                cart.pop(key, None)
            else:
                cart[key] = qty

    save_cart(cart)
    flash("Количката е обновена.")
    return redirect(url_for("cart_view"))

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart = get_cart()
    if not cart:
        flash("Количката е празна.")
        return redirect(url_for("cart_view"))

    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    product_map = {p.id: p for p in products}

    items = []
    subtotal = 0.0

    for pid_str, qty in cart.items():
        pid = int(pid_str)
        p = product_map.get(pid)
        if not p:
            continue
        qty = int(qty)
        line_total = float(p.price) * qty
        subtotal += line_total
        items.append({"product": p, "qty": qty, "line_total": line_total})
    
    if subtotal >= 80:
        shipping = 0
    else:
        shipping = 5

    total = round(subtotal + shipping, 2)
    

    if request.method == "POST":
        full_name = request.form.get("full_name")
        phone = request.form.get("phone")
        address = request.form.get("address")
        city = request.form.get("city")
        postal_code = request.form.get("postal_code")
        notes = request.form.get("notes")
        has_card = True if request.form.get("has_card") else False
        card_message = request.form.get("card_message")

        if not all([full_name, phone, address, city, postal_code]):
            flash("Попълни всички задължителни полета.")
            return redirect(url_for("checkout"))

        order = Order(
            user_id=current_user.id,
            status="created",
            total=total,
            full_name=full_name,
            phone=phone,
            address=address,
            city=city,
            postal_code=postal_code,
            notes=notes,
            has_card=has_card,
            card_message=card_message
            
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=item["product"].id,
                qty=item["qty"],
                unit_price=item["product"].price,
                line_total=item["line_total"]
            ))

        db.session.commit()
        session.pop("cart", None)

        flash("Поръчката е създадена успешно.")
        return redirect(url_for("order_detail", order_id=order.id))

    return render_template(
    "checkout.html",
    items=items,
    subtotal=subtotal,
    shipping=shipping,
    total=total
)

@app.get("/orders")
@login_required
def orders_list():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.id.desc()).all()
    return render_template("orders.html", orders=orders)

@app.get("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = db.session.get(Order, order_id)
    if not order or order.user_id != current_user.id:
        flash("Няма такава поръчка.")
        return redirect(url_for("orders_list"))

    return render_template("order_detail.html", order=order)

def ensure_admin():
    admin_email = app.config["ADMIN_EMAIL"].lower()
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            email=admin_email,
            password_hash=generate_password_hash(app.config["ADMIN_PASSWORD"]),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()

def setup_app():
    with app.app_context():
        db.create_all()
        init_db_with_products()
        ensure_admin()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        init_db_with_products()
        ensure_admin()
    app.run(debug=True)