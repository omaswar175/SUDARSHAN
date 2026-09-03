import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sudarshan-secret-key-123'

# Configures PostgreSQL for production on Render, defaults to SQLite locally
database_url = os.environ.get('DATABASE_URL', 'sqlite:///sudarshan_orders.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# User model for customer login
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)

# Database model storing customer orders & payment details
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

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            next_item = request.args.get('item', '')
            return redirect(url_for('login', next_item=next_item))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ingredients')
def ingredients():
    return render_template('ingridient.html')

# Customer Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_item = request.args.get('next_item', '')
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        next_item = request.form.get('next_item', '')
        
        user = User.query.filter_by(phone=phone, password=password).first()
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_phone'] = user.phone
            session['user_email'] = user.email
            if next_item:
                return redirect(url_for('order', item=next_item))
            return redirect(url_for('order'))
        else:
            flash("Invalid Mobile Number or Password. Please try again.")

    return render_template('login.html', next_item=next_item)

# Customer Registration Route
@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name')
    phone = request.form.get('phone')
    email = request.form.get('email')
    password = request.form.get('password')
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
    return redirect(url_for('order'))

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Protected Order Page
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

    new_order = Order(
        customer_name=name,
        email=email,
        phone=phone,
        item_name=items_summary,
        quantity="Multiple",
        address=address,
        payment_ref=payment_ref,
        status=order_status
    )
    db.session.add(new_order)
    db.session.commit()

    return render_template('order.html', success=True, customer_name=name, items_summary=items_summary, phone=phone, payment_mode=payment_mode)

@app.route('/portal', methods=['GET', 'POST'])
def user_portal():
    user_orders = None
    searched_phone = session.get('user_phone')
    customer_info = None

    if request.method == 'POST':
        searched_phone = request.form.get('phone', '').strip()

    if searched_phone:
        user_orders = Order.query.filter_by(phone=searched_phone).order_by(Order.id.desc()).all()
        if user_orders:
            customer_info = {
                'name': user_orders[0].customer_name,
                'email': user_orders[0].email,
                'phone': user_orders[0].phone
            }
            
    return render_template('user_portal.html', orders=user_orders, phone=searched_phone, customer=customer_info)

@app.route('/admin')
def admin_orders():
    secret_key = request.args.get('key')
    if secret_key != 'SudarshanAkola2026':
        return "<h1>404 Not Found</h1>", 404

    orders = Order.query.order_by(Order.id.desc()).all()
    html = """
    <html>
    <head><title>Admin Dashboard - Sudarshan Foods</title></head>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2>Customer Orders Dashboard</h2>
    <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: 100%;">
        <tr style="background-color: #d97706; color: white;">
            <th>Order ID</th><th>Customer</th><th>Phone</th><th>Email</th><th>Items & Quantities</th><th>Address</th><th>Payment Info</th><th>Status</th>
        </tr>
    """
    for o in orders:
        html += f"""
        <tr>
            <td>#{o.id}</td>
            <td><strong>{o.customer_name}</strong></td>
            <td>{o.phone}</td>
            <td>{o.email}</td>
            <td style="color: #b45309; font-weight: bold;">{o.item_name}</td>
            <td>{o.address}</td>
            <td>{o.payment_ref if o.payment_ref else 'N/A'}</td>
            <td>{o.status}</td>
        </tr>
        """
    html += "</table></body></html>"
    return html

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)