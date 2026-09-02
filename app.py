import os
from flask import Flask, render_template, request, redirect, url_for
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

# Database model for customer orders
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="New")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ingredients')
def ingredients():
    return render_template('ingridient.html')

@app.route('/order')
def order():
    selected_item = request.args.get('item', '')
    return render_template('order.html', item=selected_item)

@app.route('/place-order', methods=['POST'])
def place_order():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    item = request.form.get('item')
    quantity = request.form.get('quantity')
    address = request.form.get('address')

    new_order = Order(
        customer_name=name,
        email=email,
        phone=phone,
        item_name=item,
        quantity=quantity,
        address=address
    )
    db.session.add(new_order)
    db.session.commit()

    return render_template('order.html', item=item, success=True, customer_name=name)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)