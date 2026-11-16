import os
import random
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formatdate
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from twilio.rest import Client
import stripe

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sudarshan-secret-key-123')

# Supabase PostgreSQL (psycopg3 for Python 3.12 on Vercel) / Local SQLite URI handling
database_url = os.environ.get('DATABASE_URL', 'sqlite:///sudarshan_orders.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

# ==============================================================================
# STRIPE, SIDESHIFT, NOTIFICATION & ADMIN CONFIGURATION
# ==============================================================================
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_your_stripe_secret_key")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "pk_test_your_stripe_public_key")
SIDESHIFT_AFFILIATE_ID = os.environ.get("SIDESHIFT_AFFILIATE_ID", "LAWo3JHJh")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "omaswar175@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "tpdb awfp gcyp uaaz")
ADMIN_SECRET_CODE = os.environ.get("ADMIN_SECRET_CODE", "SudarshanAkola2026")

ADMIN_PHONE_NUMBER = "+918830446585"
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "YOUR_TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "YOUR_TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "+1234567890")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


@app.context_processor
def inject_globals():
    return dict(sideshift_affiliate_id=SIDESHIFT_AFFILIATE_ID)


def send_email_notification(customer_name, customer_email, phone, items_summary, address, payment_ref, delivery_otp):
    """Sends Delivery OTP to customer email and order alert to admin email."""
    customer_subject = "🔑 Your Delivery OTP for Sudarshan Foods Order"
    customer_body = f"""Hello {customer_name},

Thank you for ordering with Sudarshan Foods!

Items: {items_summary}
Address: {address}
Payment Info: {payment_ref}

🔑 YOUR DELIVERY VERIFICATION OTP: {delivery_otp}

Please share this code with the delivery executive upon receiving your order.
"""
    msg_customer = MIMEText(customer_body, 'plain', 'utf-8')
    msg_customer['Subject'] = customer_subject
    msg_customer['From'] = f"Sudarshan Foods <{ADMIN_EMAIL}>"
    msg_customer['To'] = customer_email
    msg_customer['Reply-To'] = ADMIN_EMAIL
    msg_customer['Date'] = formatdate(localtime=True)

    admin_subject = f"🔔 New Order Alert: {customer_name}"
    admin_body = f"""New Order Received on Sudarshan Foods!

Customer Name:    {customer_name}
Customer Email:   {customer_email}
Phone Number:     {phone}
Items Ordered:    {items_summary}
Delivery Address: {address}
Payment Info:     {payment_ref}
"""
    msg_admin = MIMEText(admin_body, 'plain', 'utf-8')
    msg_admin['Subject'] = admin_subject
    msg_admin['From'] = f"Sudarshan System <{ADMIN_EMAIL}>"
    msg_admin['To'] = ADMIN_EMAIL
    msg_admin['Date'] = formatdate(localtime=True)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(ADMIN_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(ADMIN_EMAIL, [customer_email], msg_customer.as_string())
        server.sendmail(ADMIN_EMAIL, [ADMIN_EMAIL], msg_admin.as_string())
        server.quit()
        print("✅ Order placement emails sent successfully!")
    except Exception as e:
        print(f"❌ Email notification failed: {e}")


def send_cancellation_otp_email(customer_name, customer_email, order_id, items_summary, cancel_otp):
    """Sends a 4-digit Cancellation OTP to the customer's email."""
    subject = f"⚠️ Order #{order_id} Cancellation Verification OTP - Sudarshan Foods"
    body = f"""Hello {customer_name},

A cancellation request has been initiated for your Sudarshan Foods Order #{order_id} ({items_summary}).

🔐 YOUR ORDER CANCELLATION OTP: {cancel_otp}

Please share this 4-digit code with our team only if you authorize cancelling this order.

Regards,
Sudarshan Food Production
"""
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = f"Sudarshan Foods <{ADMIN_EMAIL}>"
    msg['To'] = customer_email
    msg['Reply-To'] = ADMIN_EMAIL
    msg['Date'] = formatdate(localtime=True)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(ADMIN_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(ADMIN_EMAIL, [customer_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Failed to send cancellation OTP: {e}")
        return False


def send_delivery_confirmed_notification(customer_name, customer_email, customer_phone, order_id, items_summary, address):
    """Sends a Thank You & Delivery Receipt via Email, SMS, and WhatsApp with exact IST date and time."""
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    delivered_date = now_ist.strftime("%d %B %Y")
    delivered_time = now_ist.strftime("%I:%M %p")

    subject = f"✅ Order #{order_id} Delivered! Thank You - Sudarshan Foods"
    body = f"""Hello {customer_name},

Your Sudarshan Foods order has been successfully delivered and verified!

📦 Order ID:       #{order_id}
🍿 Items:          {items_summary}
📍 Delivered To:   {address}
📅 Delivery Date:  {delivered_date}
⏰ Delivery Time:  {delivered_time} (IST)

🙏 Thank you for choosing Sudarshan Food Production! We hope you enjoy our authentic, fresh homemade snacks. We look forward to serving you again soon!

Warm regards,
Sudarshan Food Production, Akola
"""
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = f"Sudarshan Foods <{ADMIN_EMAIL}>"
    msg['To'] = customer_email
    msg['Reply-To'] = ADMIN_EMAIL
    msg['Date'] = formatdate(localtime=True)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(ADMIN_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(ADMIN_EMAIL, [customer_email], msg.as_string())
        server.quit()
        print(f"✅ Delivery confirmation email sent to {customer_email}")
    except Exception as e:
        print(f"❌ Delivery confirmation email failed: {e}")

    if TWILIO_ACCOUNT_SID != "YOUR_TWILIO_ACCOUNT_SID":
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            target_phone = customer_phone.strip()
            if not target_phone.startswith("+"):
                target_phone = "+91" + target_phone

            sms_text = (
                f"Sudarshan Foods: Hello {customer_name}, your Order #{order_id} "
                f"({items_summary}) was delivered on {delivered_date} at {delivered_time}. "
                f"Thank you for ordering with us!"
            )

            try:
                client.messages.create(from_=TWILIO_PHONE_NUMBER, body=sms_text, to=target_phone)
            except Exception as e:
                print(f"❌ Delivery confirmation SMS failed: {e}")

            try:
                client.messages.create(
                    from_=TWILIO_WHATSAPP_NUMBER,
                    body=f"✅ *Order #{order_id} Delivered!*\nHello {customer_name}, your order ({items_summary}) was received on *{delivered_date}* at *{delivered_time}*.\n\n🙏 Thank you for choosing Sudarshan Food Production!",
                    to=f"whatsapp:{target_phone}"
                )
            except Exception as e:
                print(f"❌ Delivery confirmation WhatsApp failed: {e}")
        except Exception as e:
            print(f"❌ Twilio client error: {e}")


def send_whatsapp_and_sms(customer_name, customer_phone, items_summary, address, delivery_otp):
    if TWILIO_ACCOUNT_SID == "YOUR_TWILIO_ACCOUNT_SID":
        return
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        target_customer_phone = customer_phone.strip()
        if not target_customer_phone.startswith("+"):
            target_customer_phone = "+91" + target_customer_phone

        try:
            client.messages.create(
                from_=TWILIO_PHONE_NUMBER,
                body=f"Sudarshan Foods: Hello {customer_name}, your order for {items_summary} is placed! Your Delivery OTP is: {delivery_otp}.",
                to=target_customer_phone
            )
        except Exception as e:
            print(f"❌ Customer SMS failed: {e}")

        try:
            wa_body = (
                f"🎉 *New Order Alert!*\n"
                f"*Customer:* {customer_name}\n"
                f"*Phone:* {customer_phone}\n"
                f"*Items:* {items_summary}\n"
                f"*Address:* {address}"
            )
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body=wa_body,
                to=f"whatsapp:{ADMIN_PHONE_NUMBER}"
            )
        except Exception as e:
            print(f"❌ WhatsApp alert failed: {e}")
    except Exception as e:
        print(f"❌ Twilio error: {e}")


# ==============================================================================
# DATABASE MODELS
# ==============================================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    saved_address = db.Column(db.Text, nullable=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    item_name = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    total_amount = db.Column(db.Integer, default=0)
    address = db.Column(db.Text, nullable=False)
    payment_ref = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default="Pending Verification")
    delivery_otp = db.Column(db.String(10), nullable=True)
    cancel_otp = db.Column(db.String(10), nullable=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)          # Display title e.g. "Crispy Chakli"
    short_name = db.Column(db.String(60), nullable=False)     # Cart label e.g. "Chakli"
    badge_text = db.Column(db.String(60), default="★ BESTSELLER")
    price_250g = db.Column(db.Integer, nullable=False)
    price_500g = db.Column(db.Integer, nullable=False)
    price_1kg = db.Column(db.Integer, nullable=False)
    stock_qty = db.Column(db.Integer, default=25)             # Available packs in stock
    is_available = db.Column(db.Boolean, default=True)


def run_auto_migrations():
    """Safely adds any missing columns to existing SQLite/PostgreSQL tables."""
    with db.engine.connect() as conn:
        for sql in [
            'ALTER TABLE "user" ADD COLUMN saved_address TEXT',
            'ALTER TABLE "order" ADD COLUMN total_amount INTEGER DEFAULT 0',
            'ALTER TABLE "order" ADD COLUMN cancel_otp VARCHAR(10)'
        ]:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()


def seed_default_products():
    """Seeds initial Sudarshan Foods products if the Product table is empty."""
    if Product.query.count() == 0:
        defaults = [
            Product(
                slug="chakli",
                name="Crispy Chakli",
                short_name="Chakli",
                badge_text="★ BESTSELLER",
                price_250g=90,
                price_500g=160,
                price_1kg=310,
                stock_qty=25,
                is_available=True
            ),
            Product(
                slug="chorafalli",
                name="Special Chorafalli",
                short_name="Chorafalli",
                badge_text="🔥 FRESH BATCH",
                price_250g=85,
                price_500g=150,
                price_1kg=290,
                stock_qty=20,
                is_available=True
            ),
            Product(
                slug="makka",
                name="Roasted Makka Poha",
                short_name="Makka Poha",
                badge_text="✨ LIGHT & CRISPY",
                price_250g=70,
                price_500g=120,
                price_1kg=230,
                stock_qty=30,
                is_available=True
            ),
        ]
        db.session.add_all(defaults)
        db.session.commit()


def adjust_product_stock(items_summary, restore=False):
    """Deducts (or restores on cancel) ordered pack quantities from Product.stock_qty."""
    products = Product.query.all()
    for prod in products:
        pattern = rf"{re.escape(prod.short_name)}\s*\([^)]+\)\s*x\s*(\d+)"
        matches = re.findall(pattern, items_summary)
        if matches:
            total_packs = sum(int(m) for m in matches)
            if restore:
                prod.stock_qty = (prod.stock_qty or 0) + total_packs
                if prod.stock_qty > 0:
                    prod.is_available = True
            else:
                prod.stock_qty = max(0, (prod.stock_qty or 0) - total_packs)
                if prod.stock_qty == 0:
                    prod.is_available = False
    db.session.commit()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            next_item = request.args.get('item', '')
            return redirect(url_for('login', next_item=next_item))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('key') == ADMIN_SECRET_CODE:
            session['is_admin'] = True
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ==============================================================================
# CUSTOMER ROUTES
# ==============================================================================
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/ingredients')
def ingredients():
    return render_template('ingridient.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_item = request.args.get('next_item', '')
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        next_item = request.form.get('next_item', '')

        user = User.query.filter_by(phone=phone, password=password).first()
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_phone'] = user.phone
            session['user_email'] = user.email
            if next_item:
                return redirect(url_for('order', item=next_item))
            return redirect(url_for('user_portal'))
        else:
            flash("Invalid Mobile Number or Password. Please try again.")

    return render_template('login.html', next_item=next_item)


@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    next_item = request.form.get('next_item', '')

    existing_user = User.query.filter_by(phone=phone).first()
    if existing_user:
        flash("Mobile number is already registered. Please log in.")
        return redirect(url_for('login', next_item=next_item))

    new_user = User(name=name, phone=phone, email=email, password=password)
    db.session.add(new_user)
    db.session.commit()

    session['user_id'] = new_user.id
    session['user_name'] = new_user.name
    session['user_phone'] = new_user.phone
    session['user_email'] = new_user.email

    if next_item:
        return redirect(url_for('order', item=next_item))
    return redirect(url_for('user_portal'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/order')
@login_required
def order():
    selected_item = request.args.get('item', '')
    reorder_items = request.args.get('reorder', '')
    user = User.query.get(session.get('user_id'))
    saved_address = user.saved_address if user and user.saved_address else ''
    products = Product.query.order_by(Product.id.asc()).all()
    return render_template(
        'order.html',
        selected_item=selected_item,
        reorder_items=reorder_items,
        saved_address=saved_address,
        products=products
    )


@app.route('/place-order', methods=['POST'])
@login_required
def place_order():
    user = User.query.get(session.get('user_id'))
    name = session.get('user_name')
    email = session.get('user_email')
    phone = session.get('user_phone')

    locality = request.form.get('locality', '').strip()
    street_address = request.form.get('address', '').strip()
    full_address = f"{street_address}, {locality}, Akola" if locality else street_address

    if user and street_address:
        user.saved_address = street_address

    payment_mode = request.form.get('payment_mode')
    items_summary = request.form.get('cart_summary', '').strip()
    final_amount = int(request.form.get('final_amount', 0) or 0)

    if not items_summary or final_amount <= 0:
        flash("Please add at least one food item to your cart before ordering.")
        return redirect(url_for('order'))

    delivery_otp = str(random.randint(1000, 9999))

    # 1. STRIPE CHECKOUT FLOW
    if payment_mode == 'Stripe':
        new_order = Order(
            customer_name=name,
            email=email,
            phone=phone,
            item_name=items_summary,
            quantity="Cart",
            total_amount=final_amount,
            address=full_address,
            payment_ref="[Stripe] Pending Payment",
            status="Awaiting Stripe Payment",
            delivery_otp=delivery_otp
        )
        db.session.add(new_order)
        db.session.commit()
        adjust_product_stock(items_summary, restore=False)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'inr',
                    'product_data': {
                        'name': f"Sudarshan Foods Order #{new_order.id}",
                        'description': items_summary,
                    },
                    'unit_amount': final_amount * 100,
                },
                'quantity': 1,
            }],
            mode='payment',
            customer_email=email,
            success_url=url_for('stripe_success', order_id=new_order.id, _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for('order', _external=True),
        )
        return redirect(checkout_session.url, code=303)

    # 2. MANUAL UPI OR CASH ON DELIVERY FLOW
    if payment_mode == 'UPI':
        payment_ref = f"[UPI] {request.form.get('payment_ref')}"
        order_status = "Pending Verification"
    else:
        payment_ref = "[Cash] Cash on Delivery"
        order_status = "COD / Cash Order"

    new_order = Order(
        customer_name=name,
        email=email,
        phone=phone,
        item_name=items_summary,
        quantity="Cart",
        total_amount=final_amount,
        address=full_address,
        payment_ref=payment_ref,
        status=order_status,
        delivery_otp=delivery_otp
    )
    db.session.add(new_order)
    db.session.commit()
    adjust_product_stock(items_summary, restore=False)

    send_email_notification(name, email, phone, items_summary, full_address, payment_ref, delivery_otp)
    send_whatsapp_and_sms(name, phone, items_summary, full_address, delivery_otp)

    return render_template(
        'order.html',
        success=True,
        customer_name=name,
        items_summary=items_summary,
        phone=phone,
        payment_mode=payment_mode,
        delivery_otp=delivery_otp
    )


@app.route('/stripe-success/<int:order_id>')
@login_required
def stripe_success(order_id):
    session_id = request.args.get('session_id')
    order_obj = Order.query.get_or_404(order_id)

    if session_id:
        stripe_session = stripe.checkout.Session.retrieve(session_id)
        if stripe_session.payment_status == 'paid':
            order_obj.payment_ref = f"[Stripe Paid] {stripe_session.payment_intent}"
            order_obj.status = "Paid & Preparing"
            db.session.commit()

            send_email_notification(
                order_obj.customer_name,
                order_obj.email,
                order_obj.phone,
                order_obj.item_name,
                order_obj.address,
                order_obj.payment_ref,
                order_obj.delivery_otp
            )
            send_whatsapp_and_sms(
                order_obj.customer_name,
                order_obj.phone,
                order_obj.item_name,
                order_obj.address,
                order_obj.delivery_otp
            )

    return render_template(
        'order.html',
        success=True,
        customer_name=order_obj.customer_name,
        items_summary=order_obj.item_name,
        phone=order_obj.phone,
        payment_mode='Stripe',
        delivery_otp=order_obj.delivery_otp
    )


@app.route('/portal', methods=['GET', 'POST'])
@login_required
def user_portal():
    user_orders = None
    searched_phone = session.get('user_phone')
    if request.method == 'POST':
        searched_phone = request.form.get('phone', '').strip() or session.get('user_phone')
    if searched_phone:
        user_orders = Order.query.filter_by(phone=searched_phone).order_by(Order.id.desc()).all()
    return render_template('user_portal.html', orders=user_orders, phone=searched_phone)


@app.route('/invoice/<int:order_id>')
@login_required
def download_invoice(order_id):
    order_obj = Order.query.get_or_404(order_id)
    if order_obj.phone != session.get('user_phone') and not session.get('is_admin'):
        return "Unauthorized", 403
    ist = timezone(timedelta(hours=5, minutes=30))
    return render_template('invoice.html', order=order_obj, date_str=datetime.now(ist).strftime("%d %b %Y"))


@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session.get('user_id'))
    return render_template('profile.html', user=user)


@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    user = User.query.get(session.get('user_id'))
    if user:
        user.name = request.form.get('name', '').strip()
        user.email = request.form.get('email', '').strip()
        user.saved_address = request.form.get('saved_address', '').strip()
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.password = new_password
        db.session.commit()
        session['user_name'] = user.name
        session['user_email'] = user.email
        flash("Profile updated successfully!")
    return redirect(url_for('profile'))


# ==============================================================================
# ADMIN LOGIN, DASHBOARD, MENU PRICING & OTP ENDPOINTS
# ==============================================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        code = request.form.get('admin_code', '').strip()
        if code == ADMIN_SECRET_CODE:
            session['is_admin'] = True
            return redirect(url_for('admin_orders'))
        flash("Invalid Admin Access Code.")
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('home'))


@app.route('/admin')
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.id.desc()).all()
    products = Product.query.order_by(Product.id.asc()).all()
    total_orders = len(orders)
    pending_count = sum(1 for o in orders if "Confirmed" not in o.status and "Cancelled" not in o.status)
    completed_count = sum(1 for o in orders if "Confirmed" in o.status)
    total_revenue = sum((o.total_amount or 0) for o in orders if "Cancelled" not in o.status)

    return render_template(
        'admin.html',
        orders=orders,
        products=products,
        total_orders=total_orders,
        pending_count=pending_count,
        completed_count=completed_count,
        total_revenue=total_revenue
    )


@app.route('/admin/update-product/<int:product_id>', methods=['POST'])
@admin_required
def update_product(product_id):
    prod = Product.query.get_or_404(product_id)
    prod.name = request.form.get('name', prod.name).strip()
    prod.short_name = request.form.get('short_name', prod.short_name).strip()
    prod.price_250g = int(request.form.get('price_250g', prod.price_250g))
    prod.price_500g = int(request.form.get('price_500g', prod.price_500g))
    prod.price_1kg = int(request.form.get('price_1kg', prod.price_1kg))
    prod.stock_qty = max(0, int(request.form.get('stock_qty', prod.stock_qty)))
    prod.is_available = (request.form.get('is_available') == 'on') and (prod.stock_qty > 0)
    db.session.commit()
    return redirect(url_for('admin_orders'))


@app.route('/admin/add-product', methods=['POST'])
@admin_required
def add_product():
    name = request.form.get('name', '').strip()
    short_name = request.form.get('short_name', '').strip() or name
    badge_text = request.form.get('badge_text', '★ SPECIAL').strip()
    price_250g = int(request.form.get('price_250g', 0) or 0)
    price_500g = int(request.form.get('price_500g', 0) or 0)
    price_1kg = int(request.form.get('price_1kg', 0) or 0)
    stock_qty = max(0, int(request.form.get('stock_qty', 20) or 0))

    if name and price_500g > 0:
        slug = re.sub(r'[^a-z0-9]+', '_', short_name.lower()).strip('_')
        if Product.query.filter_by(slug=slug).first():
            slug = f"{slug}_{random.randint(10, 99)}"
        new_prod = Product(
            slug=slug,
            name=name,
            short_name=short_name,
            badge_text=badge_text,
            price_250g=price_250g or round(price_500g * 0.55),
            price_500g=price_500g,
            price_1kg=price_1kg or round(price_500g * 1.9),
            stock_qty=stock_qty,
            is_available=(stock_qty > 0)
        )
        db.session.add(new_prod)
        db.session.commit()
    return redirect(url_for('admin_orders'))


@app.route('/admin/delete-product/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    prod = Product.query.get_or_404(product_id)
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('admin_orders'))


@app.route('/send-cancel-otp', methods=['POST'])
@admin_required
def send_cancel_otp():
    order_id = request.args.get('id')
    order_obj = Order.query.get(order_id)
    if not order_obj:
        return jsonify({"success": False, "message": "Order not found"}), 404

    if "Confirmed" in order_obj.status or "Cancelled" in order_obj.status:
        return jsonify({"success": False, "message": "Order is already locked."}), 400

    cancel_otp = str(random.randint(1000, 9999))
    order_obj.cancel_otp = cancel_otp
    db.session.commit()

    email_sent = send_cancellation_otp_email(
        order_obj.customer_name,
        order_obj.email,
        order_obj.id,
        order_obj.item_name,
        cancel_otp
    )

    if email_sent:
        return jsonify({"success": True, "email": order_obj.email})
    return jsonify({"success": False, "message": "Failed to send email. Check SMTP settings."})


@app.route('/update-order-status')
@admin_required
def update_order_status():
    order_id = request.args.get('id')
    new_status = request.args.get('status')
    provided_otp = request.args.get('otp', '').strip()
    order_to_update = Order.query.get(order_id)

    if order_to_update and "Confirmed" not in order_to_update.status and "Cancelled" not in order_to_update.status:
        if new_status == "Cancelled":
            if not order_to_update.cancel_otp or provided_otp != order_to_update.cancel_otp:
                return "<script>alert('❌ Invalid Cancellation OTP! Order was NOT cancelled.'); window.location.href='/admin';</script>"
            adjust_product_stock(order_to_update.item_name, restore=True)

        order_to_update.status = new_status
        db.session.commit()

        if new_status == "Confirmed & Verified":
            send_delivery_confirmed_notification(
                order_to_update.customer_name,
                order_to_update.email,
                order_to_update.phone,
                order_to_update.id,
                order_to_update.item_name,
                order_to_update.address
            )

    return redirect(url_for('admin_orders'))


# ==============================================================================
# SAFE STARTUP INITIALIZATION (VERCEL SERVERLESS COMPATIBLE)
# ==============================================================================
with app.app_context():
    try:
        db.create_all()
        run_auto_migrations()
        seed_default_products()
    except Exception as e:
        print(f"Database init warning: {e}")

if __name__ == '__main__':
    app.run(debug=True)