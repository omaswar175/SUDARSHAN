import os
import random
import smtplib
from email.mime.text import MIMEText
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sudarshan-secret-key-123'

database_url = os.environ.get('DATABASE_URL', 'sqlite:///sudarshan_orders.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==============================================================================
# NOTIFICATION & SMS CONFIGURATION
# ==============================================================================
ADMIN_EMAIL = "omaswar175@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "tpdb awfp gcyp uaaz")

ADMIN_PHONE_NUMBER = "+918830446585"
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "YOUR_TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "YOUR_TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "+1234567890")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


def send_email_notification(customer_name, customer_email, phone, items_summary, address, payment_ref, delivery_otp):
    """Sends email notifications with the Delivery OTP to both Customer and Admin."""
    
    # 1. Customer Email
    customer_subject = "🔑 Your Delivery OTP for Sudarshan Foods Order"
    customer_body = f"""
    Hello {customer_name},

    Thank you for ordering with Sudarshan Foods!

    Items: {items_summary}
    Address: {address}
    Payment Info: {payment_ref}

    🔑 YOUR DELIVERY VERIFICATION OTP: {delivery_otp}

    Please share this code with the delivery executive upon receiving your order.
    """
    msg_customer = MIMEText(customer_body)
    msg_customer['Subject'] = customer_subject
    msg_customer['From'] = ADMIN_EMAIL
    msg_customer['To'] = customer_email

    # 2. Admin Email
    admin_subject = f"🔔 New Order Alert: {customer_name}"
    admin_body = f"""
    New Order Received on Sudarshan Foods!

    Customer Name:    {customer_name}
    Customer Email:   {customer_email}
    Phone Number:     {phone}
    Items Ordered:    {items_summary}
    Delivery Address: {address}
    Payment Info:     {payment_ref}
    🔑 DELIVERY OTP:   {delivery_otp}
    """
    msg_admin = MIMEText(admin_body)
    msg_admin['Subject'] = admin_subject
    msg_admin['From'] = ADMIN_EMAIL
    msg_admin['To'] = ADMIN_EMAIL

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(ADMIN_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(ADMIN_EMAIL, customer_email, msg_customer.as_string())
        server.sendmail(ADMIN_EMAIL, ADMIN_EMAIL, msg_admin.as_string())
        server.quit()
        print(f"✅ Email notifications sent successfully!")
    except Exception as e:
        print(f"❌ Email notification failed: {e}")


def send_whatsapp_and_sms(customer_name, customer_phone, items_summary, address, delivery_otp):
    """Sends SMS with Delivery OTP to both the Customer and Admin via Twilio."""
    if TWILIO_ACCOUNT_SID == "YOUR_TWILIO_ACCOUNT_SID":
        print("⚠️ Twilio credentials not configured. Skipping SMS alerts.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Standardize phone format for India (+91)
        target_customer_phone = customer_phone.strip()
        if not target_customer_phone.startswith("+"):
            target_customer_phone = "+91" + target_customer_phone

        # 1. SMS to Customer (Contains OTP)
        customer_msg = f"Sudarshan Foods: Hello {customer_name}, your order for {items_summary} is placed! Your Delivery OTP is: {delivery_otp}. Share this code upon delivery."
        try:
            client.messages.create(
                from_=TWILIO_PHONE_NUMBER,
                body=customer_msg,
                to=target_customer_phone
            )
            print(f"✅ SMS OTP sent to customer phone: {target_customer_phone}")
        except Exception as e:
            print(f"❌ Customer SMS failed: {e}")

        # 2. SMS to Admin (Contains Order Info & OTP)
        admin_msg = f"New Order! Customer: {customer_name} ({customer_phone}), Items: {items_summary}, OTP: {delivery_otp}"
        try:
            client.messages.create(
                from_=TWILIO_PHONE_NUMBER,
                body=admin_msg,
                to=ADMIN_PHONE_NUMBER
            )
            print(f"✅ Admin SMS sent to: {ADMIN_PHONE_NUMBER}")
        except Exception as e:
            print(f"❌ Admin SMS failed: {e}")

        # 3. WhatsApp Alert to Admin
        try:
            wa_body = (
                f"🎉 *New Order Alert!*\n"
                f"*Customer:* {customer_name}\n"
                f"*Phone:* {customer_phone}\n"
                f"*Items:* {items_summary}\n"
                f"*Address:* {address}\n"
                f"🔑 *Delivery OTP:* {delivery_otp}"
            )
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body=wa_body,
                to=f"whatsapp:{ADMIN_PHONE_NUMBER}"
            )
            print(f"✅ Admin WhatsApp sent!")
        except Exception as e:
            print(f"❌ WhatsApp alert failed: {e}")

    except Exception as e:
        print(f"❌ Twilio initialization error: {e}")


# ==============================================================================
# DATABASE MODELS
# ==============================================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    item_name = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=False)
    payment_ref = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default="Pending Verification")
    delivery_otp = db.Column(db.String(10), nullable=True)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            next_item = request.args.get('item', '')
            return redirect(url_for('login', next_item=next_item))
        return f(*args, **kwargs)
    return decorated_function


# ==============================================================================
# ROUTES
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
    return render_template('order.html', selected_item=selected_item)

@app.route('/place-order', methods=['POST'])
@login_required
def place_order():
    name = session.get('user_name')
    email = session.get('user_email')
    phone = session.get('user_phone')
    address = request.form.get('address')
    payment_mode = request.form.get('payment_mode')
    
    selected_items = []
    chakli_qty = request.form.get('chakli_qty')
    if request.form.get('chakli_check') and chakli_qty:
        selected_items.append(f"Chakli ({chakli_qty})")
        
    chorafalli_qty = request.form.get('chorafalli_qty')
    if request.form.get('chorafalli_check') and chorafalli_qty:
        selected_items.append(f"Chorafalli ({chorafalli_qty})")
        
    makka_qty = request.form.get('makka_qty')
    if request.form.get('makka_check') and makka_qty:
        selected_items.append(f"Makka Poha ({makka_qty})")

    if not selected_items:
        fallback_item = request.form.get('fallback_item', 'Custom Food Order')
        fallback_qty = request.form.get('fallback_qty', '1 kg')
        selected_items.append(f"{fallback_item} ({fallback_qty})")

    items_summary = ", ".join(selected_items)

    if payment_mode == 'UPI':
        payment_ref = f"[UPI] {request.form.get('payment_ref')}"
        order_status = "Pending Verification"
    else:
        payment_ref = "[Cash] Cash on Delivery"
        order_status = "COD / Cash Order"

    delivery_otp = str(random.randint(1000, 9999))

    new_order = Order(
        customer_name=name,
        email=email,
        phone=phone,
        item_name=items_summary,
        quantity="Multiple",
        address=address,
        payment_ref=payment_ref,
        status=order_status,
        delivery_otp=delivery_otp
    )
    db.session.add(new_order)
    db.session.commit()

    # Send Emails & SMS Alerts with OTP
    send_email_notification(name, email, phone, items_summary, address, payment_ref, delivery_otp)
    send_whatsapp_and_sms(name, phone, items_summary, address, delivery_otp)

    return render_template('order.html', success=True, customer_name=name, items_summary=items_summary, phone=phone, payment_mode=payment_mode, delivery_otp=delivery_otp)

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
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.password = new_password
        db.session.commit()
        session['user_name'] = user.name
        session['user_email'] = user.email
        flash("Profile updated successfully!")
    return redirect(url_for('profile'))

@app.route('/admin')
def admin_orders():
    secret_key = request.args.get('key')
    if secret_key != 'SudarshanAkola2026':
        return "<h1>404 Not Found</h1>", 404

    orders = Order.query.order_by(Order.id.desc()).all()
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard - Sudarshan Foods</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background-color: #f9fafb; color: #1f2937; }
            h2 { color: #b45309; }
            table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            th { background-color: #d97706; color: white; padding: 12px; text-align: left; }
            td { padding: 12px; border-bottom: 1px solid #e5e7eb; vertical-align: middle; }
            tr:hover { background-color: #fffbeb; }
            .badge { padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 0.85rem; display: inline-block; }
            .pending { background: #fef3c7; color: #92400e; }
            .confirmed { background: #d1fae5; color: #065f46; }
            .dispatched { background: #dbeafe; color: #1e40af; }
            .cancelled { background: #fee2e2; color: #991b1b; }
            .btn-action { padding: 6px 12px; margin: 2px; border: none; border-radius: 4px; font-size: 0.8rem; font-weight: bold; cursor: pointer; text-decoration: none; color: white; display: inline-block; }
            .btn-confirm { background: #059669; }
            .btn-dispatch { background: #2563eb; }
            .btn-cancel { background: #dc2626; }
        </style>
        <script>
        function confirmWithOTP(orderId, expectedOtp) {
            var userOtp = prompt("Enter the 4-digit Delivery OTP provided by the customer:");
            if (userOtp === null) return;
            if (userOtp.trim() === expectedOtp) {
                window.location.href = "/update-order-status?id=" + orderId + "&status=Confirmed%20%26%20Verified&key=SudarshanAkola2026";
            } else {
                alert("❌ Incorrect OTP! Order confirmation failed.");
            }
        }
        </script>
    </head>
    <body>
        <h2>📦 Customer Orders Management Dashboard</h2>
        <table>
            <tr>
                <th>Order ID</th>
                <th>Customer</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Items & Quantities</th>
                <th>Address</th>
                <th>Payment Ref</th>
                <th>Status</th>
                <th>Update Status</th>
            </tr>
    """
    for o in orders:
        badge_class = "pending"
        if "Confirmed" in o.status:
            badge_class = "confirmed"
        elif "Dispatched" in o.status or "Out for Delivery" in o.status:
            badge_class = "dispatched"
        elif "Cancelled" in o.status:
            badge_class = "cancelled"

        html += f"""
        <tr>
            <td><strong>#{o.id}</strong></td>
            <td>{o.customer_name}</td>
            <td>{o.phone}</td>
            <td>{o.email}</td>
            <td style="color: #b45309; font-weight: bold;">{o.item_name}</td>
            <td>{o.address}</td>
            <td>{o.payment_ref if o.payment_ref else 'N/A'}</td>
            <td><span class="badge {badge_class}">{o.status}</span></td>
            <td>
                <button class="btn-action btn-confirm" onclick="confirmWithOTP('{o.id}', '{o.delivery_otp}')">Confirm (OTP)</button>
                <a class="btn-action btn-dispatch" href="/update-order-status?id={o.id}&status=Out%20for%20Delivery&key=SudarshanAkola2026">Dispatch</a>
                <a class="btn-action btn-cancel" href="/update-order-status?id={o.id}&status=Cancelled&key=SudarshanAkola2026">Cancel</a>
            </td>
        </tr>
        """
    html += "</table></body></html>"
    return html

@app.route('/update-order-status')
def update_order_status():
    secret_key = request.args.get('key')
    if secret_key != 'SudarshanAkola2026':
        return "<h1>Unauthorized</h1>", 401

    order_id = request.args.get('id')
    new_status = request.args.get('status')
    order_to_update = Order.query.get(order_id)
    if order_to_update:
        order_to_update.status = new_status
        db.session.commit()

    return redirect(url_for('admin_orders', key='SudarshanAkola2026'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)