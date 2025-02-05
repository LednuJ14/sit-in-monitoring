from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "your_secret_key"

USERS = {
    "12345": {"password": "password123", "email": "admin@example.com", "name":
"Admin User"}
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    idno = request.form.get("idno")
    password = request.form.get("password")

    if idno in USERS and USERS[idno]["password"] == password:
        return redirect(url_for("success"))
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
    
    if idno in USERS:
        flash("User already exists", "error")
        return redirect(url_for("home"))
    
    USERS[idno] = {
        "password": password,
        "email": email,
        "lastname": lastname,
        "firstname": firstname,
        "middlename": middlename,
        "course": course,
        "yearlevel": yearlevel
    }

    flash("Registration successful! Please login.", "success")
    return redirect(url_for("home"))
    
@app.route("/success")
def success():
    return "Login Successful!"

if __name__ == "__main__":
    app.run(debug=True)
