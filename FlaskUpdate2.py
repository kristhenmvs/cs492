# -*- coding: utf-8 -*-

"""

@author: Alandis, Elijah, Jessica, Kristhen, James

"""

import logging
import os
import random
import sqlite3
import string
import threading
import time
import webbrowser

from flask import Flask, request, render_template, redirect, session, jsonify

from flask_session import Session

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
                cursor.execute(insert_query, (user_id, customer['id'], today, book['SalePrice'], book['ID']))

        conn.commit()
        conn.close()
        return jsonify({'message': 'Checkout successful'})
    except Exception as e:
        logging.error(f"Error during checkout: {e}")
        return jsonify({'message': 'Checkout failed'}), 500

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()

    # Add a short delay to ensure the server is up
    time.sleep(2)

    # Path to the Chrome executable
    chrome_path = 'C:/Program Files/Google/Chrome/Application/chrome.exe %s'

    # Open the local webpage in Chrome
    webbrowser.get(chrome_path).open_new_tab('http://127.0.0.1:5000/login')
