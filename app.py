import os
from flask import Flask, render_template, request, redirect, url_for, session
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

# Database model storing customer accounts and profiles
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    address = db.Column(db.Text, nullable=False)
    orders = db.relationship('Order', backref='customer', lazy=True)

# Database model storing customer orders & payment details
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    item_name = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=False)
    payment_ref = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default="Pending Verification")

@app.route('/')
def home():
    user_orders = None
    customer = None
    if 'user_phone' in session:
        customer = Customer.query.filter_by(phone=session['user_phone']).first()
        if customer:
            user_orders = Order.query.filter_by(phone=customer.phone).order_by(Order.id.desc()).all()
    return render_template('index.html', customer=customer, orders=user_orders)

@app.route('/register-portal', methods=['POST'])
def register_portal():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address')

    if phone:
        existing_customer = Customer.query.filter_by(phone=phone).first()
        if not existing_customer:
            new_customer = Customer(name=name, email=email, phone=phone, address=address)
            db.session.add(new_customer)
            db.session.commit()
            session['user_phone'] = phone
        else:
            session['user_phone'] = existing_customer.phone

    # Automatically takes customer to snack ordering form upon registration
    return redirect(url_for('order'))

@app.route('/login-portal', methods=['POST'])
def login_portal():
    phone = request.form.get('phone', '').strip()
    customer = Customer.query.filter_by(phone=phone).first()
    if customer:
        session['user_phone'] = customer.phone
        return redirect(url_for('order'))
    
    return redirect(url_for('home', require_login=True))

@app.route('/logout-portal')
def logout_portal():
    session.pop('user_phone', None)
    return redirect(url_for('home'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ingredients')
def ingredients():
    return render_template('ingridient.html')

@app.route('/order')
def order():
    # Enforces customer registration before purchasing snacks
    if 'user_phone' not in session:
        return redirect(url_for('home', require_login=True) + '#customer-portal')
    
    customer = Customer.query.filter_by(phone=session['user_phone']).first()
    if not customer:
        session.pop('user_phone', None)
        return redirect(url_for('home', require_login=True) + '#customer-portal')

    selected_item = request.args.get('item', '')
    return render_template('order.html', selected_item=selected_item, customer=customer)

@app.route('/place-order', methods=['POST'])
def place_order():
    if 'user_phone' not in session:
        return redirect(url_for('home', require_login=True) + '#customer-portal')

    customer = Customer.query.filter_by(phone=session['user_phone']).first()
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
        payment_ref_val = request.form.get('payment_ref', '')
        payment_ref = f"[UPI] {payment_ref_val}"
        order_status = "Pending Verification"
    else:
        payment_ref = "[Cash] Cash on Delivery"
        order_status = "COD / Cash Order"

    new_order = Order(
        customer_id=customer.id,
        customer_name=customer.name,
        email=customer.email,
        phone=customer.phone,
        item_name=items_summary,
        quantity="Multiple",
        address=customer.address,
        payment_ref=payment_ref,
        status=order_status
    )
    db.session.add(new_order)
    db.session.commit()

    return render_template('order.html', 
                           success=True, 
                           order_id=new_order.id, 
                           customer=customer, 
                           items_summary=items_summary, 
                           payment_ref=payment_ref,
                           payment_mode=payment_mode)

@app.route('/admin')
def admin_orders():
    secret_key = request.args.get('key')
    ADMIN_SECRET_KEY = 'SudarshanAkola2026'
    
    if secret_key != ADMIN_SECRET_KEY:
        return "<h1>404 Not Found</h1><p>The requested URL was not found on the server.</p>", 404

    orders = Order.query.order_by(Order.id.desc()).all()
    html = """
    <html>
    <head>
        <title>Admin Dashboard - Sudarshan Foods</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9fafb;">
    <h2 style="color: #b45309;">Customer Orders Dashboard</h2>
    <div style="overflow-x: auto;">
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: 100%; background: #ffffff;">
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
            <td style="color: #059669; font-weight: bold;">{o.payment_ref if o.payment_ref else 'N/A'}</td>
            <td>{o.status}</td>
        </tr>
        """
    html += "</table></div></body></html>"
    return html

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)