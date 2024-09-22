# -*- coding: utf-8 -*-

"""

@author: Alandis, Elijah, Jessica, Kristhen, James

"""

from flask import Flask, request, render_template, redirect, session, jsonify
import sqlite3
from flask_session import Session
import webbrowser
import threading
import time
import logging
import string
import os
import random
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'our_secret_code'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)


def run_flask_app():
    app.run(debug=True, use_reloader=False)

# Function to connect to the SQLite database
def connect_db():
    logging.debug("Connecting to the Database")
    conn = sqlite3.connect('CTUTeamProject.db')
    conn.row_factory = sqlite3.Row  # This allows us to return rows as dictionaries
    return conn

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')


@app.route('/all_inventory')
def all_inventory():
    conn = connect_db()
    cursor = conn.cursor()
    query = "SELECT * FROM BookInfo INNER JOIN BookInventory ON BookInfo.ID = BookInventory.BookInfoID"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return render_template('inventory_list.html', books=rows)


@app.route('/selected_inventory')
def selected_inventory():
    book_id = request.args.get('bookId')
    conn = connect_db()
    cursor = conn.cursor()
    query = "SELECT * FROM BookInfo INNER JOIN BookInventory ON BookInfo.ID = BookInventory.BookInfoID WHERE BookInfo.ID = ? OR BookInfo.Title LIKE ?"
    cursor.execute(query, (book_id, '%' + book_id + '%'))
    rows = cursor.fetchall()
    conn.close()
    return render_template('inventory_list.html', books=rows)


@app.route('/save_inventory', methods=['POST'])
def save_inventory():
    data = request.get_json()
    book_id = data['bookId']
    new_stock_min = data['stockMin']
    new_stock_max = data['stockMax']
    new_on_hand_qty = data['onHandQty']
    username = session.get('username', 'Unknown')  # Get the username from the session

    conn = connect_db()
    cursor = conn.cursor()

    # Fetch the current inventory values
    query = "SELECT StockMin, StockMax, OnHandQty FROM BookInventory WHERE BookInfoID = ?"
    cursor.execute(query, (book_id,))
    current_values = cursor.fetchone()

    if current_values:
        prior_stock_min = current_values['StockMin']
        prior_stock_max = current_values['StockMax']
        prior_on_hand_qty = current_values['OnHandQty']

        # Insert a new record into InventoryAdjustments
        insert_query = "INSERT INTO InventoryAdjustments (BookInfoID, PriorMin, PriorMax, PriorOh, NewMin, NewMax, User) VALUES (?, ?, ?, ?, ?, ?, ?)"

        cursor.execute(insert_query, (book_id, prior_stock_min, prior_stock_max, prior_on_hand_qty, new_stock_min, new_stock_max, username))

        # Update the BookInventory table
        update_query = "UPDATE BookInventory SET StockMin = ?, StockMax = ?, OnHandQty = ? WHERE BookInfoID = ?"
        cursor.execute(update_query, (new_stock_min, new_stock_max, new_on_hand_qty, book_id))
        conn.commit()
        conn.close()

        return {'message': 'Inventory updated successfully'}
    else:
        conn.close()
        return {'message': 'Book not found'}





# Route to look up a book by title, author, or ID
@app.route('/lookup_book', methods=['GET'])
def lookup_book():
    title = request.args.get('title', None)
    author = request.args.get('author', None)
    bookid = request.args.get('bookid', None)

    if not title and not author and not bookid:
        return render_template('error.html', message="Please provide a title, author, or ID to look up")

    conn = connect_db()
    cursor = conn.cursor()

    # Building query based on whether title, author, or ID is provided
    if title:
        query = "SELECT * FROM BookInfo INNER JOIN BookInventory ON BookInfo.ID = BookInventory.BookInfoID WHERE title LIKE ?"
        cursor.execute(query, ('%' + title + '%',))
    elif author:
        query = "SELECT * FROM BookInfo INNER JOIN BookInventory ON BookInfo.ID = BookInventory.BookInfoID WHERE author LIKE ?"
        cursor.execute(query, ('%' + author + '%',))
    elif bookid:
        query = "SELECT * FROM BookInfo INNER JOIN BookInventory ON BookInfo.ID = BookInventory.BookInfoID WHERE ID LIKE ?"
        cursor.execute(query, ('%' + bookid + '%',))
    rows = cursor.fetchall()
    conn.close()

    if rows:
        auth_level = session.get('auth_level', 'Customer')
        return render_template('book_list.html', books=rows, auth_level=auth_level)
    else:
        return render_template('error.html', message="No books found")


@app.template_filter('currency')
def currency_filter(value):
    return "${:,.2f}".format(value)


@app.route('/check_login', methods=['POST'])
def check_login():
    username = request.form['username']
    password = request.form['password']

    conn = connect_db()
    cursor = conn.cursor()

    # Query to check if the provided username and password match
    query = "SELECT * FROM LogInfo WHERE UserNm = ? AND PsWrd = ?"
    cursor.execute(query, (username, password))
    user = cursor.fetchone()
    conn.close()

    logging.debug(f"User fetched from database: {user}")

    if user:
        session['username'] = username
        session['auth_level'] = user[4]
        logging.warning(f"Username: {user[0]}, Auth Level: {user[4]}")
        return render_template('success.html', username=username)
    else:
        return render_template('error.html', message="Invalid username or password")


@app.route('/search')
def search():
    if 'username' in session and 'auth_level' in session:
        username = session['username']
        auth_level = session['auth_level']
        return render_template('book_search.html', username=username, auth_level=auth_level)
    else:
        return redirect('/login')


@app.route('/login')
def login_form():
    return render_template('login.html')

@app.route('/cart')
def cart():
    if 'username' in session and 'auth_level' in session:
        username = session['username']
        auth_level = session['auth_level']
        return render_template('cart.html', username=username, auth_level=auth_level)
    else:
        return redirect('/login')

from datetime import datetime

@app.route('/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        cart = data['cart']
        customer_info = data['customerInfo'] or 10000  # Default if customer doesn't have an acct.
        logging.debug(customer_info)
        auth_level = session.get('auth_level')
        user_nm = session.get('username')
        today = datetime.today().strftime('%Y-%m-%d')  # Get today's date

        conn = connect_db()
        cursor = conn.cursor()

        # Fetch the user ID from the LogInfo table
        logging.warning(user_nm)
        cursor.execute("SELECT UserID FROM LogInfo WHERE UserNm = ?", (user_nm,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'message': f'User with username {user_nm} not found!'}), 404
        user_id = user['UserID']

        for item in cart:
            book_id = item['id']
            cursor.execute("SELECT * FROM BookInfo WHERE ID = ?", (book_id,))
            book = cursor.fetchone()

            if not book:
                conn.close()
                return jsonify({'message': f'Book with ID {book_id} not found!'}), 404

            logging.warning(f"book Data: {dict(book)}")
            if auth_level in ['Employee', 'Supervisor']:
                customer_code = customer_info
                cursor.execute("SELECT * FROM CustomerInfo WHERE ID = ?", (customer_code,))
                customer = cursor.fetchone()
                if not customer:
                    conn.close()
                    return jsonify({'message': f'Customer with code {customer_code} not found!'}), 404

                insert_query = """
                    INSERT INTO SalesRecords (SoldBy, SoldTo, SalesDate, SalesPrice, BookSold)
                    VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(insert_query, (user_id, customer['id'], today, book['SalePrice'], book['ID']))
            else:
                cursor.execute("""
                    SELECT CustomerInfo.id 
                    FROM CustomerInfo 
                    INNER JOIN LogInfo ON LogInfo.UserEmail = CustomerInfo.Email_Add 
                    WHERE LogInfo.UserNm = ?
                """, (customer_info,))
                customer = cursor.fetchone()
                logging.warning(customer[0])
                logging.warning(book['SalePrice'])
                logging.warning(book['ID'])
                if not customer:
                    conn.close()
                    return jsonify({'message': f'Customer with username {customer_info} not found!'}), 404

                insert_query = """
                    INSERT INTO SalesRecords (SoldBy, SoldTo, SalesDate, SalesPrice, BookSold)
                    VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(insert_query, (customer[0], customer[0], today, book['SalePrice'], book['ID']))

            # Reduce OnHandQty by 1 in the BookInventory table
            update_query = "UPDATE BookInventory SET OnHandQty = OnHandQty - 1 WHERE BookInfoID = ?"
            cursor.execute(update_query, (book_id,))

        conn.commit()
        conn.close()
        return redirect('/checkout_success')
    except Exception as e:
        logging.warning(f"Error during checkout: {e}")
        return jsonify({'message': 'An error occurred during checkout.'}), 500

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/checkout_success')
def checkout_success():
    return render_template('checkout_success.html')

@app.route('/save_registration', methods=['POST'])
def save_registration():
    data = request.get_json()
    userName = data['UserNm']
    userPassword = data['PsWrd']
    userEmail = data['UserEmail']
    userAuth = data['AuthLevel']
    userPh = data['PhoneNumber']
    useraddr = data['Address']
    usercity = data['City']
    userfirst = data['FirstName']
    userlast = data['LastName']
    today = datetime.today().strftime('%Y-%m-%d')  # Get today's date

    conn = connect_db()
    cursor = conn.cursor()

    # Fetch the current max UserID
    cursor.execute("SELECT COALESCE(MAX(UserID), 0) FROM LogInfo")
    currentID = cursor.fetchone()[0]
    # newUserID = currentID + 1
    if userAuth in ('Supervisor' , 'Employee'):
        # Instert a Sup/Emp Entry
        insert_query = "INSERT INTO LogInfo (UserNm, PsWrd, UserEmail, AuthLevel) VALUES (?, ?, ?, ?)"
        cursor.execute(insert_query, (userName, userPassword, userEmail, userAuth))
    else:
        # Check if email already exists in CustomerInfo
        cursor.execute("SELECT * FROM CustomerInfo WHERE Email_Add = ?", (userEmail,))
        existing_customer = cursor.fetchone()

        if existing_customer:
            # If the customer already exists, just insert into LogInfo
            insert_loginfo_query = "INSERT INTO LogInfo (UserNm, PsWrd, UserEmail, AuthLevel) VALUES (?, ?, ?, ?)"
            cursor.execute(insert_loginfo_query, (userName, userPassword, userEmail, userAuth))
            conn.commit()
            conn.close()

            session['username'] = userName
            session['auth_level'] = userAuth

            return jsonify({'message': 'Registration successful.', 'updated_info': {'username': userName, 'auth_level': userAuth}})
        
        else:
           
            # Insert Customer entry into LogInfo
            insert_query = "INSERT INTO LogInfo (UserNm, PsWrd, UserEmail, AuthLevel) VALUES (?, ?, ?, ?)"
            cursor.execute(insert_query, (userName, userPassword, userEmail, userAuth))
            conn.commit()

            # Insert Customer entry into CustomerInfo
            insert_customer_query = """
                    INSERT INTO CustomerInfo (Email_Add, First_Name, Last_Name, Start_date, Ph_num, Phy_Add, Phy_Add_City)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
            cursor.execute(insert_customer_query, (userEmail, userfirst, userlast, today, userPh, useraddr, usercity))

            conn.commit()
            conn.close()

            # return {'message': 'Registration successful.'}
            session['username'] = userName
            session['auth_level'] = userAuth

            return jsonify({'message': 'Registration successful.', 'updated_info': {'username': userName, 'auth_level': userAuth}})

@app.route('/reports')
def reports():
    auth_level = session.get('auth_level')
    return render_template('reports.html', auth_level=auth_level)

# Inventory Stock Ordering
@app.route('/stock_order_report')
def stock_order_reports():
    auth_level = session.get('auth_level')
    return render_template('stock_order_report.html', auth_level=auth_level)
# Path to the database
DB_PATH = 'CTUTeamProject.db'


@app.route('/fetch_stock_order_report')
def fetch_stock_order_report():
    conn = connect_db()
    query = '''
    SELECT 
        BookInfo.ID, 
        BookInfo.Title, 
        BookInventory.OnHandQty, 
        BookInventory.StockMin, 
        BookInventory.StockMax, 
        printf('$%.2f', BookInfo.Cost) as BookCost, 
        (BookInventory.StockMax - BookInventory.OnHandQty) as OrderQty, 
        printf('$%.2f', (BookInventory.StockMax - BookInventory.OnHandQty) * BookInfo.Cost) as TotalCost
    FROM 
        BookInventory
    JOIN 
        BookInfo ON BookInventory.BookInfoID = BookInfo.ID
    WHERE 
        BookInventory.OnHandQty < BookInventory.StockMin OR BookInventory.OnHandQty = 0
    '''
    cursor = conn.execute(query)
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()

    if rows:
        data = {
            "success": True,
            "columns": columns,
            "rows": [tuple(row) for row in rows]
        }
    else:
        data = {
            "success": False,
            "message": "No data available"
        }

    return jsonify(data)

#Function to create Stock Order
@app.route('/place_order', methods=['POST'])
def place_order():
    order_data = request.json
    order_id = ''.join(random.choices(string.digits, k=10)) + '.txt'
    order_path = os.path.join('orders', order_id)

    if not os.path.exists('orders'):
        os.makedirs('orders')

    with open(order_path, 'w') as file:
        for item in order_data:
            file.write(f"ID: {item['ID']}, OrderQty: {item['orderQty']}, TotalCost: {item['totalCost']}\n")

    return jsonify({"success": True, "order_id": order_id})

# Function to query the database
def query_database(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()
    return rows, columns

# Generate report based on sales item or customer
@app.route('/generate_report', methods=['GET'])
def generate_report():
    report_type = request.args.get('type', None)


    if report_type == 'item':
        query = """
            SELECT sr.BookSold AS BookID, bi.Title, bi.SalePrice, bi2.StockMin, bi2.StockMax, COUNT(sr.BookSold) AS TotalSold
            FROM SalesRecords sr
            JOIN BookInfo bi ON sr.BookSold = bi.ID
            JOIN BookInventory bi2 ON bi.ID = bi2.BookInfoID
            GROUP BY sr.BookSold, bi.Title, bi.SalePrice, bi2.StockMin, bi2.StockMax
            ORDER BY sr.BookSold;
        """
    elif report_type == 'customer':
        query = """
            SELECT CI.First_Name, CI.Last_Name, COUNT(SR.SoldTo) AS TotalSalesRecords
            FROM CustomerInfo CI
            JOIN SalesRecords SR ON CI.ID = SR.SoldTo
            GROUP BY CI.First_Name, CI.Last_Name;
        """
    else:
        return jsonify({"success": False, "message": "Invalid report type"})

    rows, columns = query_database(query)
    if rows:
        return jsonify({"success": True, "rows": rows, "columns": columns})
    else:
        return jsonify({"success": False, "message": "No data found"})
    
@app.route('/customers')
def customers():
    return render_template('customers.html')


@app.route('/all_customer')
def all_customer():
    conn = connect_db()
    cursor = conn.cursor()
    query = "SELECT * FROM CustomerInfo"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return render_template('customer_list.html', customers=rows)


@app.route('/selected_customer')
def selected_customer():
    customer_id = request.args.get('customerId')
    conn = connect_db()
    cursor = conn.cursor()
    query = "SELECT * FROM CustomerInfo WHERE CustomerInfo.Id = ? OR CustomerInfo.First_Name LIKE ?"
    cursor.execute(query, (customer_id, '%' + customer_id + '%'))
    rows = cursor.fetchall()
    conn.close()
    return render_template('customer_list.html', customers=rows)


@app.route('/save_customer', methods=['POST'])
def save_customer():
    data = request.get_json()
    
    if not data:
        return jsonify({'message': 'No data provided'}), 400

    customer_id = data.get('Id')
    new_First_Name = data.get('First_Name')
    new_Last_Name = data.get('Last_Name')
    new_Email_Add = data.get('Email_Add')
    new_Ph_Num = data.get('Ph_Num')
    new_Phy_Add = data.get('Phy_Add')
    new_Phy_Add_City = data.get('Phy_Add_City')

    if not all([customer_id, new_First_Name, new_Last_Name, new_Email_Add, new_Ph_Num, new_Phy_Add, new_Phy_Add_City]):
        return jsonify({'message': 'Missing customer data'}), 400

    conn = connect_db()
    cursor = conn.cursor()

    # Fetch the current customer data
    query = "SELECT First_Name, Last_Name, Email_Add, Ph_Num, Phy_Add, Phy_Add_City FROM CustomerInfo WHERE Id = ?"
    cursor.execute(query, (customer_id,))
    current_values = cursor.fetchone()

    if current_values:
        current_email = current_values[3]

        # Update the customer info in the database
        update_query = """
        UPDATE CustomerInfo 
        SET First_Name = ?, Last_Name = ?, Email_Add = ?, Ph_Num = ?, Phy_Add = ?, Phy_Add_City = ? 
        WHERE Id = ?
        """
        cursor.execute(update_query, (new_First_Name, new_Last_Name, new_Email_Add, new_Ph_Num, new_Phy_Add, new_Phy_Add_City, customer_id))
        
        # Check if the email has changed
        if new_Email_Add != current_email:
            # Update the email in LogInfo as well
            update_loginfo_query = "UPDATE LogInfo SET UserEmail = ? WHERE UserEmail = ?"
            cursor.execute(update_loginfo_query, (new_Email_Add, current_email))

        conn.commit()
        conn.close()
        return jsonify({'message': 'Customer updated successfully', 'updated_info': data}), 200
    else:
        conn.close()
        return jsonify({'message': 'Customer not found'}), 404

@app.route('/add_customer', methods=['POST'])
def add_customer():
    data = request.get_json()
    new_First_Name = data['First_Name']
    new_Last_Name = data['Last_Name']
    new_Email_Add = data['Email_Add']
    new_Ph_Num = data['Ph_Num']
    new_Phy_Add = data['Phy_Add']
    new_Phy_Add_City = data['Phy_Add_City']
    
    # Insert new customer into the database
    conn = connect_db()
    cursor = conn.cursor()

    # Assuming there is an INSERT query to add a new customer
    insert_query = """
        INSERT INTO CustomerInfo (First_Name, Last_Name, Email_Add, Ph_Num, Phy_Add, Phy_Add_City)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    cursor.execute(insert_query, (new_First_Name, new_Last_Name, new_Email_Add, new_Ph_Num, new_Phy_Add, new_Phy_Add_City))
    conn.commit()
    conn.close()

    # Return success message
    return jsonify({"success": True, "message": "Customer added successfully"})

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()

    # Add a short delay to ensure the server is up
    time.sleep(2)

    # Path to the Chrome executable
    chrome_paths = [
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        'C:/Users/{}/AppData/Local/Google/Chrome/Application/chrome.exe'.format(os.getlogin())
    ]

    # Find the Chrome executable
    chrome_path = None
    for path in chrome_paths:
        if shutil.which(path):
            chrome_path = path
            break

    if chrome_path:
        # Register the new browser type
        webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))
        # Open the local webpage in Chrome
        webbrowser.get('chrome').open_new_tab('http://127.0.0.1:5000/login')
    else:
        print("Chrome executable not found in common paths.")





