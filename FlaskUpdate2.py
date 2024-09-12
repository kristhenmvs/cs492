# -*- coding: utf-8 -*-

"""

@author: Alandis, Elijah, Jessica, Kristhen, James

"""

from flask import Flask, request, render_template, redirect, session
import sqlite3
from flask_session import Session
import webbrowser
import threading
import time
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'our_secret_code'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)


def run_flask_app():
    app.run(debug=True, use_reloader=False)


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


# Function to connect to the SQLite database
def connect_db():
    logging.debug("Connecting to the Database")
    conn = sqlite3.connect('CTUTeamProject.db')
    conn.row_factory = sqlite3.Row  # This allows us to return rows as dictionaries
    return conn


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


@app.route('/sales')
def sales():
    if 'username' in session and 'auth_level' in session:
        auth_level = session['auth_level']
        if auth_level in ['Supervisor', 'Employee']:
            # Example book data, replace with actual data from your database
            book = {
                'Title': 'Example Book Title',
                'Author': 'Example Author',
                'ReleaseDate': '2024-01-01',
                'ID': '12345',
                'AisleLoc': 'A1',
                'ShelfLoc': 'S1',
                'OnHandQty': 10,
                'SalePrice': 19.99
            }
            return render_template('sales.html', book=book)
        else:
            return render_template('error.html', message="You do not have permission to view this page.")
    else:
        return redirect('/login')


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


@app.route('/')
def home():
    return render_template('index.html')


if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()

    # Add a short delay to ensure the server is up
    time.sleep(2)

    # Path to the Chrome executable
    chrome_path = 'C:/Program Files/Google/Chrome/Application/chrome.exe %s'

    # Open the local webpage in Chrome
    webbrowser.get(chrome_path).open_new_tab('http://127.0.0.1:5000/login')

