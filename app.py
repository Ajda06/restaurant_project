from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
from datetime import datetime

app = Flask(__name__)
app.secret_key = '6'

# Свързване с MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1234",
    database="restaurant_db"
)

# HOME
@app.route('/')
def home():
    return render_template('index.html')

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect(url_for('admin_panel' if user['is_admin'] else 'client_panel'))
        else:
            return "Грешно потребителско име или парола"
    return render_template('login.html')

# SIGNUP
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']
        if password != confirm:
            return "Паролите не съвпадат"

        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (%s, %s, 0)", (username, password))
            db.commit()
            return redirect(url_for('login'))
        except mysql.connector.errors.IntegrityError:
            return "Потребителското име вече съществува"
    return render_template('signup.html')

# MENU
@app.route('/menu')
def redirect_menu_html():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM dishes WHERE availability = 1")
    dishes = cursor.fetchall()
    return render_template("menu.html", dishes=dishes)

# ORDER FORM
@app.route('/order/<int:dish_id>', methods=['GET', 'POST'])
def order_form(dish_id):
    if request.method == 'POST':
        name = request.form['customer_name']
        phone = request.form['phone']
        quantity = int(request.form['quantity'])
        address = request.form['address']
        email = request.form.get('email', None)

        cursor = db.cursor()
        try:
            cursor.execute("""
                INSERT INTO orders (dish_id, customer_name, phone, quantity, address, email)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (dish_id, name, phone, quantity, address, email))
            db.commit()
            return render_template("order_success.html", dish_id=dish_id)
        except Exception as e:
            print("Order error:", e)
            db.rollback()
            return "Грешка при записа на поръчката.", 500
    else:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM dishes WHERE id = %s", (dish_id,))
        dish = cursor.fetchone()
        return render_template("order.html", dish=dish)

# QUICK ORDER (без форма)
@app.route('/make_order/<int:dish_id>')
def quick_order(dish_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT price FROM dishes WHERE id = %s", (dish_id,))
    dish = cursor.fetchone()
    if not dish:
        return "Невалидно ястие"

    total_price = dish['price']

    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO orders (user_id, dish_id, total_price, status)
        VALUES (%s, %s, %s, %s)
    """, (user_id, dish_id, total_price, 'active'))
    db.commit()

    return redirect(url_for('redirect_menu_html'))

# CLIENT PANEL
@app.route('/client_panel')
def client_panel():
    if session.get('is_admin') == 0:
        return render_template('client_panel.html')
    if session.get('is_admin') == 1:
        return redirect(url_for('admin_panel'))
    return redirect(url_for('login'))


@app.route('/add_to_cart/<int:dish_id>')
def add_to_cart(dish_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, name, price FROM dishes WHERE id = %s", (dish_id,))
    dish = cursor.fetchone()
    cursor.close()

    if not dish:
        return "Невалидно ястие"

    if 'cart' not in session:
        session['cart'] = []

    for item in session['cart']:
        if item['dish_id'] == dish['id']:
            item['quantity'] += 1
            break
    else:
        session['cart'].append({
            'dish_id': dish['id'],
            'name': dish['name'],
            'price': float(dish['price']),
            'quantity': 1
        })

    return redirect(url_for('redirect_menu_html'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session or 'cart' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cart = session['cart']
    cursor = db.cursor()

    for item in cart:
        cursor.execute("""
            INSERT INTO orders (user_id, dish_id, total_price, status)
            VALUES (%s, %s, %s, %s)
        """, (user_id, item['dish_id'], item['price'] * item['quantity'], 'active'))

    db.commit()
    session.pop('cart')  # изчистване на количката
    return render_template('order_success.html')
@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('view_cart'))
@app.route('/remove_from_cart/<int:dish_id>', methods=['POST'])
def remove_from_cart(dish_id):
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] if item['dish_id'] != dish_id]
    return redirect(url_for('view_cart'))

# MY ORDERS
@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, d.name AS dish_name, o.total_price, o.status, o.order_time
        FROM orders o
        JOIN dishes d ON o.dish_id = d.id
        WHERE o.user_id = %s
        ORDER BY o.order_time DESC
    """, (user_id,))
    orders = cursor.fetchall()
    return render_template('my_orders.html', orders=orders)

# RESERVATIONS
@app.route('/reserve', methods=['GET', 'POST'])
def make_reservation():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        date = request.form['date']
        time = request.form['time']
        guests = request.form['guests']
        user_id = session['user_id']

        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO reservations (user_id, customer_name, phone, date, time, guests)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, name, phone, date, time, guests))
        db.commit()
        return redirect(url_for('client_panel'))

    return render_template('reserve.html')

@app.route('/my_reservations')
def my_reservations():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, customer_name, phone, date, time, guests, created_at
        FROM reservations
        WHERE user_id = %s
        ORDER BY date DESC, time DESC
    """, (user_id,))
    reservations = cursor.fetchall()
    return render_template('my_reservations.html', reservations=reservations)

# ADMIN PANEL
@app.route('/admin')
def admin_panel():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    return render_template('admin_panel.html')

@app.route('/manage_menu')
def manage_menu():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM dishes")
    dishes = cursor.fetchall()
    return render_template('manage_menu.html', dishes=dishes)

@app.route('/add_dish', methods=['GET', 'POST'])
def add_dish():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = request.form['price']
        description = request.form['description']
        availability = request.form.get('availability', '0')
        image_filename = request.form['image_filename']

        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO dishes (name, category, price, description, availability, image_filename)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, category, price, description, availability, image_filename))
        db.commit()
        return redirect(url_for('manage_menu'))

    return render_template('add_dish.html')

@app.route('/edit_dish/<int:dish_id>', methods=['GET', 'POST'])
def edit_dish(dish_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = request.form['price']
        description = request.form['description']
        availability = request.form.get('availability', '0')
        image_filename = request.form['image_filename']

        cursor.execute("""
            UPDATE dishes
            SET name=%s, category=%s, price=%s, description=%s, availability=%s, image_filename=%s
            WHERE id=%s
        """, (name, category, price, description, availability, image_filename, dish_id))
        db.commit()
        return redirect(url_for('manage_menu'))

    cursor.execute("SELECT * FROM dishes WHERE id = %s", (dish_id,))
    dish = cursor.fetchone()
    if not dish:
        return "Ястието не съществува."
    return render_template('edit_dish.html', dish=dish)

@app.route('/delete_dish/<int:dish_id>')
def delete_dish(dish_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor()
    cursor.execute("DELETE FROM dishes WHERE id = %s", (dish_id,))
    db.commit()
    return redirect(url_for('manage_menu'))

@app.route('/view_orders')
def view_orders():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, u.username, d.name AS dish_name, o.total_price, o.status, o.order_time
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN dishes d ON o.dish_id = d.id
        ORDER BY o.order_time DESC
    """)
    orders = cursor.fetchall()
    return render_template('view_orders.html', orders=orders)

@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        status = request.form['status']
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
        db.commit()
        return redirect(url_for('view_orders'))

    cursor.execute("""
        SELECT o.*, u.username, d.name AS dish_name
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN dishes d ON o.dish_id = d.id
        WHERE o.id = %s
    """, (order_id,))
    order = cursor.fetchone()
    if not order:
        return "Поръчката не съществува."
    return render_template('edit_order.html', order=order)

@app.route('/delete_order/<int:order_id>')
def delete_order(order_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor()
    cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
    db.commit()
    return redirect(url_for('view_orders'))

@app.route('/view_reservations')
def view_reservations():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.id, u.username, r.customer_name, r.phone, r.date, r.time, r.guests, r.created_at
        FROM reservations r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.date DESC, r.time DESC
    """)
    reservations = cursor.fetchall()
    return render_template('view_reservations.html', reservations=reservations)

@app.route('/view_staff')
def manage_employees():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM employees ORDER BY id DESC")
    staff = cursor.fetchall()
    return render_template('view_staff.html', staff=staff)

@app.route('/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
def edit_employee(employee_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        phone = request.form['phone']

        cursor.execute("""
            UPDATE employees
            SET name = %s, role = %s, phone = %s
            WHERE id = %s
        """, (name, role, phone, employee_id))
        db.commit()
        return redirect(url_for('manage_employees'))

    cursor.execute("SELECT * FROM employees WHERE id = %s", (employee_id,))
    employee = cursor.fetchone()
    if not employee:
        return "Служителят не съществува."
    return render_template('edit_employee.html', employee=employee)

@app.route('/delete_employee/<int:employee_id>')
def delete_employee(employee_id):
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    cursor = db.cursor()
    cursor.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
    db.commit()
    return redirect(url_for('manage_employees'))

@app.route('/add_employees/', methods=['GET', 'POST'])
def add_employee():
    if session.get('is_admin') != 1:
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        phone = request.form['phone']
        cursor = db.cursor()
        cursor.execute("INSERT INTO employees (name, role, phone) VALUES (%s, %s, %s)", (name, role, phone))
        db.commit()
        return redirect('/view_staff')
    return render_template('add_employee.html')


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')
    

@app.route('/delete_reservation/<int:reservation_id>')
def delete_reservation(reservation_id):
    cursor = db.cursor()
    cursor.execute("DELETE FROM reservations WHERE id = %s", (reservation_id,))
    db.commit()
    return redirect(url_for('view_reservations'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
