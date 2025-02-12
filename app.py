from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import Error

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="sit_in_system"
    )

app = Flask(__name__)
app.secret_key = "your_secret_key"

USERS = {
    "admin": {"password": "user", "email": "admin@example.com", "name":
"Admin User"}
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    idno = request.form.get("idno")
    password = request.form.get("password")


    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE idno = %s AND password = %s", (idno, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['user_id'] = user['idno']  
        return redirect(url_for("dashboard"))
    else:
        flash("Invalid ID No. or password", "error")
        return redirect(url_for("home"))
        
@app.route("/register", methods=["POST"])
def register():
    idno = request.form.get("idno")
    lastname = request.form.get("lastname")
    firstname = request.form.get("firstname")
    middlename = request.form.get("middlename") 
    course = request.form.get("course")
    yearlevel = request.form.get("yearlevel")
    email = request.form.get("email")
    password = request.form.get("password")
    repeat_password = request.form.get("repeat_password")

    if not all([idno, lastname, firstname, course, yearlevel, email, password, repeat_password]):
        flash("All fields except Middle Name are required!", "error")
        return redirect(url_for("home"))
    
    if password != repeat_password:
        flash("Passwords do not match. Please try again.", "error")
        return redirect(url_for("home"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE idno = %s", (idno,))
        if cursor.fetchone():
            flash("User already exists", "error")
            return redirect(url_for("home"))
        
        cursor.execute("INSERT INTO users (idno, lastname, firstname, middlename, course, yearlevel, email, password) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                       (idno, lastname, firstname, middlename, course, yearlevel, email, password))
        conn.commit()
        conn.close()

        flash("Registration successful! Please login.", "success")
    except Error as e:
        flash(f"Database error: {e}", "error")

    return redirect(url_for("home"))



# Dashboard Route - Displays user profile after login
@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))  # Redirect to home if user is not logged in

    user_id = session['user_id']

    # Fetch user details from the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE idno = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return render_template("dashboard.html", user=user)  # Pass user data to template
    else:
        flash("User not found", "error")
        return redirect(url_for('home'))  # Redirect to home if user is not found


if __name__ == "__main__":
    app.run(debug=True)
