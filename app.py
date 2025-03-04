from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
import re
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

# Admin login credentials (for simplicity, using hardcoded values)
ADMIN_CREDENTIALS = {
    "admin": {"password": "user", "email": "admin@example.com", "name": "Admin User"}
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    idno = request.form.get("idno")
    password = request.form.get("password")

    # Check if admin
    if idno in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[idno]["password"] == password:
        session["admin"] = idno
        return redirect(url_for("admin_dashboard"))

    # Check if student
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE idno = %s AND password = %s", (idno, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['user_id'] = user['idno']  
        return redirect(url_for("student_dashboard"))
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

    remaining_sessions = 30 if course in ["BSIT", "BSCS"] else 15

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

@app.route("/admin_dashboard")
def admin_dashboard():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    return render_template("admin/admin_dashboard.html", admin=ADMIN_CREDENTIALS[session["admin"]])

@app.route("/student_dashboard")
def student_dashboard():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE idno = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return render_template("student/student_dashboard.html", user=user)
    else:
        flash("User not found", "error")
        return redirect(url_for('home'))
    
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE idno = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return render_template('student/profile.html', user=user)
    else:
        flash("User not found", "error")
        return redirect(url_for('home'))

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch current user data
    cursor.execute("SELECT * FROM users WHERE idno = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        flash("User not found", "error")
        return redirect(url_for('home'))

    if request.method == "POST":
        firstname = request.form.get("firstname", "").strip()
        middlename = request.form.get("middlename", "").strip()
        lastname = request.form.get("lastname", "").strip()
        course = request.form.get("course", "").strip()
        yearlevel = request.form.get("yearlevel", "").strip()
        email = request.form.get("email", "").strip()

        # Validate required fields
        if not all([firstname, lastname, course, yearlevel, email]):
            flash("All fields except Middle Name are required!", "error")
            return redirect(url_for("edit_profile"))

        # Validate yearlevel (must be a number)
        if not yearlevel.isdigit():
            flash("Year level must be a number!", "error")
            return redirect(url_for("edit_profile"))

        # Validate email format
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            flash("Invalid email format!", "error")
            return redirect(url_for("edit_profile"))

        # Check if there are any changes
        if (
            firstname == user["firstname"] and
            middlename == user["middlename"] and
            lastname == user["lastname"] and
            course == user["course"] and
            yearlevel == str(user["yearlevel"]) and
            email == user["email"]
        ):
            flash("No changes were made to your profile.", "info")
            return redirect(url_for("edit_profile"))

        # Update the profile if there are changes
        try:
            cursor.execute("""
                UPDATE users
                SET firstname = %s, middlename = %s, lastname = %s, course = %s, yearlevel = %s, email = %s
                WHERE idno = %s
            """, (firstname, middlename, lastname, course, yearlevel, email, user_id))
            
            conn.commit()
            flash("Profile updated successfully!", "success")
        except Error as e:
            flash(f"Error updating profile: {e}", "error")

        return redirect(url_for("profile"))

    cursor.close()
    conn.close()
    return render_template("student/profile.html", user=user)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
