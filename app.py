from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import mysql.connector
import re
from mysql.connector import Error
from datetime import datetime
import pandas as pd
import io
import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import markupsafe
import traceback
import random
import string
from werkzeug.security import generate_password_hash
import psycopg2
import psycopg2.extras

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="sit_in_system"
    )

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Add the nl2br filter for templates
@app.template_filter('nl2br')
def nl2br(value):
    if value:
        value = markupsafe.escape(value)
        return markupsafe.Markup(value.replace('\n', '<br>'))
    return ''

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
    cursor.execute("SELECT * FROM students WHERE idno = %s AND password = %s", (idno, password))
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
    
    # Validate course input against allowed values
    allowed_courses = ["BSIT", "BSCS", "BSBA", "BSA", "BSHM", "BSE", "BSCJ"]
    if course not in allowed_courses:
        flash(f"Invalid course. Allowed courses are: {', '.join(allowed_courses)}", "error")
        return redirect(url_for("home"))
    
    # Validate yearlevel input
    try:
        yearlevel_int = int(yearlevel)
        if yearlevel_int < 1 or yearlevel_int > 5:
            flash("Year level must be between 1 and 5", "error")
            return redirect(url_for("home"))
    except ValueError:
        flash("Year level must be a number", "error")
        return redirect(url_for("home"))

    remaining_sessions = 30 if course in ["BSIT", "BSCS"] else 15

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE idno = %s", (idno,))
        if cursor.fetchone():
            flash("User already exists", "error")
            return redirect(url_for("home"))
        
        cursor.execute("INSERT INTO students (idno, lastname, firstname, middlename, course, yearlevel, email, password, remaining_sessions) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                       (idno, lastname, firstname, middlename, course, yearlevel_int, email, password, remaining_sessions))
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
    
    # Get statistics for the dashboard
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get total students
        cursor.execute("SELECT COUNT(*) as total FROM students")
        total_students = cursor.fetchone()['total']
        
        # Get total sit-ins
        cursor.execute("SELECT COUNT(*) as total FROM sit_ins")
        total_sit_ins = cursor.fetchone()['total']
        
        # Get today's sit-ins
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) as total FROM sit_ins WHERE DATE(start_time) = %s", (today,))
        todays_sit_ins = cursor.fetchone()['total']
        
        # Get active sit-ins
        cursor.execute("SELECT COUNT(*) as total FROM sit_ins WHERE end_time IS NULL")
        active_sit_ins = cursor.fetchone()['total']
        
        # Get pending feedback
        cursor.execute("SELECT COUNT(*) as total FROM feedback WHERE is_read = FALSE")
        pending_feedback = cursor.fetchone()['total']
        
        # Get recent activities (combined sit-ins and feedback)
        cursor.execute("""
            (SELECT 'sit_in' as type, s.id, u.firstname, u.lastname, u.idno, s.purpose, s.lab_room, s.start_time as timestamp
             FROM sit_ins s
             JOIN students u ON s.student_id = u.idno
             ORDER BY s.start_time DESC LIMIT 5)
            UNION ALL
            (SELECT 'feedback' as type, f.id, u.firstname, u.lastname, u.idno, f.subject, NULL as lab_room, f.created_at as timestamp
             FROM feedback f
             JOIN students u ON f.student_id = u.idno
             ORDER BY f.created_at DESC LIMIT 5)
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        recent_activities = cursor.fetchall()

        # Statistics: Get course distribution for dashboard stats
        cursor.execute("""
            SELECT u.course, COUNT(*) as count 
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            GROUP BY u.course
            ORDER BY count DESC
            LIMIT 5
        """)
        course_data = [{"label": row["course"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Statistics: Get lab room usage
        cursor.execute("""
            SELECT lab_room, COUNT(*) as count 
            FROM sit_ins 
            GROUP BY lab_room
            ORDER BY count DESC
        """)
        lab_room_data = [{"label": row["lab_room"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Get announcements for dashboard
        cursor.execute("""
            SELECT id, title, content, visibility, created_at, expiry_date, created_by
            FROM announcements
            WHERE (expiry_date IS NULL OR expiry_date > NOW())
            ORDER BY created_at DESC
            LIMIT 5
        """)
        announcements = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/admin_dashboard.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            total_students=total_students,
            total_sit_ins=total_sit_ins,
            todays_sit_ins=todays_sit_ins,
            active_sit_ins=active_sit_ins,
            pending_feedback=pending_feedback,
            recent_activities=recent_activities,
            today=today,
            # New additions for statistics and announcements
            course_data=course_data,
            lab_room_data=lab_room_data,
            announcements=announcements,
            now=datetime.now()
        )
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template("admin/admin_dashboard.html", admin=ADMIN_CREDENTIALS[session["admin"]])

@app.route("/admin_student_search")
def admin_student_search():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    return render_template("admin/student_search.html", admin=ADMIN_CREDENTIALS[session["admin"]])

@app.route("/api/search_student")
def api_search_student():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    student_id = request.args.get("id", "")
    if not student_id:
        return jsonify({"error": "Student ID is required"}), 400
    
    # Clean up the student ID to handle common issues
    student_id = student_id.strip()
    
    print(f"DEBUG: Searching for student with ID: '{student_id}'")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # DEBUGGING: First list all students to verify the database connection
        print(f"DEBUG: Database connection established successfully")
        
        # Check the database encoding
        cursor.execute("SHOW VARIABLES LIKE 'character_set_database'")
        charset = cursor.fetchone()
        print(f"DEBUG: Database character set: {charset}")
        
        # List first 20 students to help debug
        cursor.execute("SELECT idno, firstname, lastname FROM students LIMIT 20")
        all_students = cursor.fetchall()
        print(f"DEBUG: First 20 students in database:")
        for student in all_students:
            print(f"  - ID: '{student['idno']}' (type: {type(student['idno'])}) Name: {student['firstname']} {student['lastname']}")
        
        # Prepare different formats of the ID to try
        id_variations = [
            student_id,                                      # Original format
            student_id.lstrip('0'),                          # Without leading zeros
            student_id.zfill(8),                             # With leading zeros (8 digits)
            student_id.replace('-', ''),                     # Without hyphens
            student_id.replace(' ', ''),                     # Without spaces
            f"{student_id[:4]}-{student_id[4:]}" if len(student_id) >= 8 else student_id  # Add hyphen after 4 digits
        ]
        
        # Try to find student with any of the ID variations
        found_student = None
        used_variation = None
        
        for variation in id_variations:
            print(f"DEBUG: Trying ID variation: '{variation}'")
            cursor.execute("""
                SELECT idno, firstname, lastname, course, yearlevel, email, remaining_sessions
                FROM students 
                WHERE idno = %s
            """, (variation,))
            
            student = cursor.fetchone()
            if student:
                found_student = student
                used_variation = variation
                print(f"DEBUG: Match found with variation: '{variation}'")
                break
        
        # If still no match, try LIKE search as last resort
        if not found_student:
            print(f"DEBUG: No exact match with variations, trying LIKE search")
            cursor.execute("""
                SELECT idno, firstname, lastname, course, yearlevel, email, remaining_sessions
                FROM students 
                WHERE idno LIKE %s
            """, (f"%{student_id}%",))
            found_student = cursor.fetchone()
            if found_student:
                used_variation = "LIKE match"
                print(f"DEBUG: Found with LIKE search: '{found_student['idno']}'")
        
        cursor.close()
        conn.close()
        
        if found_student:
            print(f"DEBUG: Student found: {found_student['firstname']} {found_student['lastname']}")
            
            return jsonify({
                "found": True,
                "id": found_student['idno'],
                "name": f"{found_student['firstname']} {found_student['lastname']}",
                "course": found_student['course'],
                "year_level": found_student['yearlevel'],
                "email": found_student['email'],
                "remaining_sessions": found_student['remaining_sessions'],
                "matched_with": used_variation
            })
        else:
            print(f"DEBUG: No student found with ID: '{student_id}' or variations")
            
            # Return debugging info about tried variations
            return jsonify({
                "found": False,
                "debug_info": {
                    "searched_id": student_id,
                    "tried_variations": id_variations,
                    "id_type": str(type(student_id))
                }
            })
            
    except Error as e:
        error_message = str(e)
        print(f"DEBUG: Database error during student search: {error_message}")
        traceback_info = traceback.format_exc()
        print(f"DEBUG: Traceback: {traceback_info}")
        return jsonify({"error": error_message, "traceback": traceback_info}), 500

@app.route("/api/create_sit_in", methods=["POST"])
def api_create_sit_in():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    student_id = data.get("student_id")
    purpose = data.get("purpose")
    lab = data.get("lab")
    
    if not all([student_id, purpose, lab]):
        return jsonify({"error": "All fields are required"}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if student exists
        cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404
        
        # Check if student has active sit-in
        cursor.execute("SELECT * FROM sit_ins WHERE student_id = %s AND end_time IS NULL", (student_id,))
        active_sit_in = cursor.fetchone()
        
        if active_sit_in:
            return jsonify({
                "success": False, 
                "message": "Student already has an active sit-in session"
            }), 400
        
        # Check remaining sessions
        if student['remaining_sessions'] <= 0:
            return jsonify({
                "success": False, 
                "message": "Student has no remaining sessions"
            }), 400
        
        # Create new sit-in with status automatically set to 'approved' since admin is creating it
        cursor.execute("""
            INSERT INTO sit_ins (student_id, purpose, lab_room, start_time, created_by, status)
            VALUES (%s, %s, %s, NOW(), %s, 'approved')
        """, (student_id, purpose, lab, session["admin"]))
        
        sit_in_id = cursor.lastrowid
        
        # Create a notification for the student
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
            VALUES (%s, 'sit_in', %s, %s, NOW(), 0)
        """, (
            student_id, 
            f"Admin created a sit-in session for you in {lab} for purpose: {purpose}.",
            sit_in_id
        ))
        
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True, 
            "id": sit_in_id,
            "message": "Sit-in created successfully. Session count will be deducted when the session ends.",
            "remaining_sessions": student['remaining_sessions']
        })
        
    except Error as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/admin_sit_in_records")
def admin_sit_in_records():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    # Get page number and records per page
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Get filter parameters
    student_id = request.args.get('student_id', '')
    course = request.args.get('course', '')
    lab_room = request.args.get('lab_room', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    status = request.args.get('status', '')
    search_bar = request.args.get('search_bar', '')  # Add search_bar parameter

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Initialize query and params
        base_query = """
            SELECT s.id, s.student_id, u.firstname, u.lastname, u.course, s.purpose, 
                   s.lab_room, s.start_time, s.end_time, s.created_by
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) as total FROM sit_ins s JOIN students u ON s.student_id = u.idno WHERE 1=1"
        params = []
        
        # Dynamically add conditions based on the filters
        conditions = []

        if student_id:
            conditions.append("s.student_id = %s")
            params.append(student_id)

        if course:
            conditions.append("u.course = %s")
            params.append(course)

        if lab_room:
            conditions.append("s.lab_room = %s")
            params.append(lab_room)

        if start_date:
            conditions.append("DATE(s.start_time) >= %s")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(s.start_time) <= %s")
            params.append(end_date)

        if status == "active":
            conditions.append("s.end_time IS NULL")
        elif status == "completed":
            conditions.append("s.end_time IS NOT NULL")

        if search_bar:
            conditions.append("""
                (u.firstname LIKE %s OR u.lastname LIKE %s OR s.student_id LIKE %s OR u.course LIKE %s OR s.purpose LIKE %s OR s.lab_room LIKE %s)
            """)
            search_term = f"%{search_bar}%"
            params.extend([search_term, search_term, search_term, search_term, search_term , search_term])

        # Apply conditions to the query if they exist
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
            count_query += " AND " + " AND ".join(conditions)

        # Add ordering and pagination to the query
        base_query += " ORDER BY s.start_time DESC LIMIT %s OFFSET %s"
        offset = (page - 1) * per_page
        
        # Get total record count
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page  # Ceiling division
        
        # Execute the main query with pagination parameters
        cursor.execute(base_query, params + [per_page, offset])
        sit_in_records = cursor.fetchall()
        
        # Get statistics for the view
        # 1. Unique students
        cursor.execute("""
            SELECT COUNT(DISTINCT s.student_id) as count
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1 """ + (" AND " + " AND ".join(conditions) if conditions else ""), params)
        unique_students = cursor.fetchone()['count']
        
        # 2. Average duration in minutes
        cursor.execute("""
            SELECT AVG(TIMESTAMPDIFF(MINUTE, s.start_time, IFNULL(s.end_time, NOW()))) as avg_duration
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1 """ + (" AND " + " AND ".join(conditions) if conditions else ""), params)
        avg_duration = cursor.fetchone()['avg_duration'] or 0
        
        # 3. Active sessions count
        active_sessions_query = count_query + " AND s.end_time IS NULL"
        cursor.execute(active_sessions_query, params)
        active_sessions = cursor.fetchone()['total']
        
        # 4. Distribution by course
        cursor.execute("""
            SELECT u.course as label, COUNT(*) as value
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1 """ + (" AND " + " AND ".join(conditions) if conditions else "") + " GROUP BY u.course ORDER BY value DESC", params)
        course_data = cursor.fetchall()
        
        # 5. Distribution by lab room
        cursor.execute("""
            SELECT s.lab_room as label, COUNT(*) as value
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1 """ + (" AND " + " AND ".join(conditions) if conditions else "") + " GROUP BY s.lab_room ORDER BY value DESC", params)
        lab_room_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/sit_in_records.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            sit_in_records=sit_in_records,
            page=page,
            total_pages=total_pages,
            # New statistics data
            total_records=total_records,
            unique_students=unique_students,
            avg_duration=avg_duration,
            active_sessions=active_sessions,
            course_data=course_data,
            lab_room_data=lab_room_data
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template("admin/sit_in_records.html", admin=ADMIN_CREDENTIALS[session["admin"]])



@app.route("/admin_feedback")
def admin_feedback():
    if "admin" not in session:
        flash("Admin access required", "error")
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all feedback with student and session information
        # Using the correct table names and join conditions
        cursor.execute("""
            SELECT f.*, s.student_id, 
                   CONCAT(st.firstname, ' ', st.lastname) as student_name,
                   s.lab_room as laboratory
            FROM feedback f
            JOIN sit_ins s ON f.session_id = s.id
            JOIN students st ON f.student_id = st.idno
            ORDER BY f.created_at DESC
        """)
        
        feedback_list = cursor.fetchall()
        conn.close()
        
        return render_template("admin/feedback.html", feedback_list=feedback_list)
    except Exception as e:
        print(e)
        flash("An error occurred while retrieving feedback", "error")
        return redirect(url_for("admin_dashboard"))

@app.route("/admin_mark_feedback_read/<int:feedback_id>", methods=["POST"])
def admin_mark_feedback_read(feedback_id):
    if "admin" not in session:
        return jsonify({"success": False, "message": "Admin access required"})

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Mark feedback as read
        cursor.execute(
            "UPDATE feedback SET is_read = TRUE WHERE id = %s",
            (feedback_id,)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Feedback marked as read"})
    except Exception as e:
        print(e)
        return jsonify({"success": False, "message": "An error occurred while updating feedback"})

@app.route("/admin_respond_feedback/<int:feedback_id>", methods=["POST"])
def admin_respond_feedback(feedback_id):
    if "admin" not in session:
        flash("Admin access required", "error")
        return redirect(url_for("login"))
    
    # This function is no longer needed since we're using a simpler is_read status
    # Instead, just mark the feedback as read
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Mark feedback as read
        cursor.execute(
            "UPDATE feedback SET is_read = TRUE WHERE id = %s",
            (feedback_id,)
        )
        
        conn.commit()
        conn.close()
        
        flash("Feedback marked as read", "success")
    except Exception as e:
        print(e)
        flash("An error occurred while updating feedback", "error")
    
    return redirect(url_for("admin_feedback"))

@app.route("/admin_statistics")
def admin_statistics():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    # Get date range from query parameters
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    chart_type = request.args.get("chart_type", "daily")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build date filter condition
        date_filter = ""
        params = []
        
        if start_date:
            date_filter += " AND DATE(start_time) >= %s"
            params.append(start_date)
        
        if end_date:
            date_filter += " AND DATE(start_time) <= %s"
            params.append(end_date)
        
        # Get total sit-ins
        cursor.execute(f"SELECT COUNT(*) as total FROM sit_ins WHERE 1=1{date_filter}", params)
        total_sit_ins = cursor.fetchone()['total']
        
        # Get unique students
        cursor.execute(f"SELECT COUNT(DISTINCT student_id) as total FROM sit_ins WHERE 1=1{date_filter}", params)
        unique_students = cursor.fetchone()['total']
        
        # Get average duration in minutes
        cursor.execute(f"""
            SELECT AVG(TIMESTAMPDIFF(MINUTE, start_time, IFNULL(end_time, NOW()))) as avg_duration 
            FROM sit_ins 
            WHERE 1=1{date_filter}
        """, params)
        avg_duration = cursor.fetchone()['avg_duration'] or 0
        
        # Get peak hour
        cursor.execute(f"""
            SELECT HOUR(start_time) as hour, COUNT(*) as count 
            FROM sit_ins 
            WHERE 1=1{date_filter}
            GROUP BY HOUR(start_time) 
            ORDER BY count DESC 
            LIMIT 1
        """, params)
        peak_hour_data = cursor.fetchone()
        peak_hour = f"{peak_hour_data['hour']}:00" if peak_hour_data else "N/A"
        peak_count = peak_hour_data['count'] if peak_hour_data else 0
        
        # Get activity data based on chart type
        group_by = ""
        date_format = ""
        
        if chart_type == "daily":
            group_by = "DATE(start_time)"
            date_format = "%Y-%m-%d"
        elif chart_type == "weekly":
            group_by = "YEARWEEK(start_time)"
            date_format = "Week %v, %Y"
        elif chart_type == "monthly":
            group_by = "EXTRACT(YEAR_MONTH FROM start_time)"
            date_format = "%b %Y"
        
        cursor.execute(f"""
            SELECT {group_by} as date_group, DATE_FORMAT(start_time, %s) as formatted_date, COUNT(*) as count 
            FROM sit_ins 
            WHERE 1=1{date_filter}
            GROUP BY date_group 
            ORDER BY date_group
        """, [date_format] + params)
        
        activity_data = [{"label": row["formatted_date"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Get distribution by course
        cursor.execute(f"""
            SELECT u.course, COUNT(*) as count 
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1{date_filter}
            GROUP BY u.course
        """, params)
        
        course_data = [{"label": row["course"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Get distribution by purpose
        cursor.execute(f"""
            SELECT purpose, COUNT(*) as count 
            FROM sit_ins 
            WHERE 1=1{date_filter}
            GROUP BY purpose
        """, params)
        
        purpose_data = [{"label": row["purpose"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Get lab room usage
        cursor.execute(f"""
            SELECT lab_room, COUNT(*) as count 
            FROM sit_ins 
            WHERE 1=1{date_filter}
            GROUP BY lab_room
        """, params)
        
        lab_room_data = [{"label": row["lab_room"], "value": row["count"]} for row in cursor.fetchall()]
        
        # Get year level distribution
        cursor.execute(f"""
            SELECT u.yearlevel, COUNT(*) as count 
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1{date_filter}
            GROUP BY u.yearlevel
            ORDER BY u.yearlevel
        """, params)
        
        year_level_data = [{"label": f"Year {row['yearlevel']}", "value": row["count"]} for row in cursor.fetchall()]
        
        # Get time distribution (morning, afternoon, evening)
        cursor.execute(f"""
            SELECT 
                CASE 
                    WHEN HOUR(start_time) < 12 THEN 'Morning (before 12pm)'
                    WHEN HOUR(start_time) < 17 THEN 'Afternoon (12pm-5pm)'
                    ELSE 'Evening (after 5pm)'
                END as time_period,
                COUNT(*) as count 
            FROM sit_ins 
            WHERE 1=1{date_filter}
            GROUP BY time_period
        """, params)
        
        time_distribution_data = [{"label": row["time_period"], "value": row["count"]} for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/statistics.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            total_sit_ins=total_sit_ins,
            unique_students=unique_students,
            avg_duration=int(avg_duration),
            peak_hour=peak_hour,
            peak_count=peak_count,
            activity_data=activity_data,
            course_data=course_data,
            purpose_data=purpose_data,
            lab_room_data=lab_room_data,
            year_level_data=year_level_data,
            time_distribution_data=time_distribution_data,
            start_date=start_date,
            end_date=end_date,
            chart_type=chart_type
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template("admin/statistics.html", admin=ADMIN_CREDENTIALS[session["admin"]])

@app.route("/admin_announcements", methods=["GET", "POST"])
def admin_announcements():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        visibility = request.form.get("visibility")
        expiry_date = request.form.get("expiry_date") or None
        
        if not all([title, content, visibility]):
            flash("Title, content, and visibility are required", "error")
            return redirect(url_for("admin_announcements"))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO announcements (title, content, visibility, expiry_date, created_by)
                VALUES (%s, %s, %s, %s, %s)
            """, (title, content, visibility, expiry_date, session["admin"]))
            
            announcement_id = cursor.lastrowid
            
            # Create notifications for students based on announcement visibility
            if visibility == 'all':
                cursor.execute("""
                    INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
                    SELECT idno, 'announcement', %s, %s, NOW(), 0
                    FROM students
                """, (f"New Announcement: {title}", announcement_id))
            else:
                # Insert for specific course students (bsit or bscs)
                cursor.execute("""
                    INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
                    SELECT idno, 'announcement', %s, %s, NOW(), 0
                    FROM students
                    WHERE course = %s
                """, (f"New Announcement: {title}", announcement_id, visibility.upper()))
            
            conn.commit()
            flash("Announcement created successfully", "success")
            
            cursor.close()
            conn.close()
            
            # Determine where to redirect based on the referer
            referer = request.headers.get('Referer', '')
            if '/admin_dashboard' in referer:
                return redirect(url_for("admin_dashboard"))
            
        except Error as e:
            flash(f"Database error: {e}", "error")
    
    # Get all announcements
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, title, content, visibility, created_at, expiry_date, created_by
            FROM announcements
            ORDER BY created_at DESC
        """)
        
        announcements = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/announcements.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            announcements=announcements,
            now=datetime.now()
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template("admin/announcements.html", admin=ADMIN_CREDENTIALS[session["admin"]], now=datetime.now())

@app.route("/delete_announcement/<int:announcement_id>", methods=["POST"])
def delete_announcement(announcement_id):
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash("Announcement deleted successfully", "success")
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for("admin_announcements"))

@app.route("/student_dashboard")
def student_dashboard():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
    student = cursor.fetchone()
    
    # Fetch announcements for this student based on their course or 'all' visibility
    announcements = []
    if student:
        # Get course-specific and 'all' announcements that haven't expired
        cursor.execute("""
            SELECT id, title, content, visibility, created_at, expiry_date
            FROM announcements
            WHERE (visibility = %s OR visibility = 'all')
            AND (expiry_date IS NULL OR expiry_date > NOW())
            ORDER BY created_at DESC
        """, (student['course'].lower(),))
        announcements = cursor.fetchall()
    
    conn.close()

    if student:
        return render_template("student/student_dashboard.html", user=student, announcements=announcements, now=datetime.now())
    else:
        flash("Student not found", "error")
        return redirect(url_for('home'))
    
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    if student:
        return render_template('student/profile.html', user=student)
    else:
        flash("Student not found", "error")
        return redirect(url_for('home'))

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch current student data
    cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
    student = cursor.fetchone()

    if not student:
        flash("Student not found", "error")
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
            firstname == student["firstname"] and
            middlename == student["middlename"] and
            lastname == student["lastname"] and
            course == student["course"] and
            yearlevel == str(student["yearlevel"]) and
            email == student["email"]
        ):
            flash("No changes were made to your profile.", "info")
            return redirect(url_for("edit_profile"))

        # Update the profile if there are changes
        try:
            cursor.execute("""
                UPDATE students
                SET firstname = %s, middlename = %s, lastname = %s, course = %s, yearlevel = %s, email = %s
                WHERE idno = %s
            """, (firstname, middlename, lastname, course, yearlevel, email, student_id))
            
            conn.commit()
            flash("Profile updated successfully!", "success")
        except Error as e:
            flash(f"Error updating profile: {e}", "error")

        return redirect(url_for("profile"))

    cursor.close()
    conn.close()
    return render_template("student/profile.html", user=student)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("home"))

@app.route("/admin_end_sit_in/<int:sit_in_id>", methods=["POST"])
def admin_end_sit_in(sit_in_id):
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get the student ID for this sit-in
        cursor.execute("SELECT student_id FROM sit_ins WHERE id = %s AND end_time IS NULL", (sit_in_id,))
        sit_in = cursor.fetchone()
        
        if not sit_in:
            flash("Sit-in session already ended or not found", "error")
            return redirect(url_for("admin_sit_in_records"))
        
        student_id = sit_in['student_id']
        
        # Update sit-in record to mark as ended
        cursor.execute("""
            UPDATE sit_ins 
            SET end_time = NOW() 
            WHERE id = %s AND end_time IS NULL
        """, (sit_in_id,))
        
        if cursor.rowcount > 0:
            # Now deduct one session from the student's remaining sessions
            cursor.execute("""
                UPDATE students
                SET remaining_sessions = GREATEST(remaining_sessions - 1, 0)
                WHERE idno = %s
            """, (student_id,))
            
            # Create a notification for the student
            cursor.execute("""
                INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
                VALUES (%s, 'sit_in', %s, %s, NOW(), 0)
            """, (
                student_id, 
                "Your lab session has been ended by an administrator. One session has been deducted from your remaining sessions.",
                sit_in_id
            ))
            
            flash("Sit-in session ended successfully and session count deducted", "success")
        else:
            flash("Sit-in session already ended or not found", "error")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for("admin_sit_in_records"))

@app.route("/admin_export_records", methods=["GET"])
def admin_export_records():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    export_format = request.args.get("format", "csv")
    
    # Get query parameters for filtering
    student_id = request.args.get("student_id", "")
    course = request.args.get("course", "")
    lab_room = request.args.get("lab_room", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    status = request.args.get("status", "")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build query with filters
        query = """
            SELECT s.id, s.student_id, u.firstname, u.lastname, u.course, s.purpose, 
                   s.lab_room, s.start_time, s.end_time, 
                   IFNULL(TIMESTAMPDIFF(MINUTE, s.start_time, s.end_time), 0) as duration_minutes
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1
        """
        params = []
        
        if student_id:
            query += " AND s.student_id = %s"
            params.append(student_id)
        
        if course:
            query += " AND u.course = %s"
            params.append(course)
        
        if lab_room:
            query += " AND s.lab_room = %s"
            params.append(lab_room)
        
        if start_date:
            query += " AND DATE(s.start_time) >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND DATE(s.start_time) <= %s"
            params.append(end_date)
        
        if status == "active":
            query += " AND s.end_time IS NULL"
        elif status == "completed":
            query += " AND s.end_time IS NOT NULL"
        
        query += " ORDER BY s.start_time DESC"
        
        cursor.execute(query, params)
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not records:
            flash("No records found to export", "error")
            return redirect(url_for("admin_sit_in_records"))
        
        # Prepare data for export
        filename = f"sit_in_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if export_format == "csv":
            return export_csv(records, filename)
        elif export_format == "excel":
            return export_excel(records, filename)
        elif export_format == "pdf":
            return export_pdf(records, filename)
        else:
            flash("Invalid export format", "error")
            return redirect(url_for("admin_sit_in_records"))
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("admin_sit_in_records"))

def export_csv(records, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Student ID', 'Student Name', 'Course', 'Purpose', 'Lab Room', 'Start Time', 'End Time', 'Duration (minutes)'])
    
    # Write data rows
    for record in records:
        writer.writerow([
            record['id'],
            record['student_id'],
            f"{record['firstname']} {record['lastname']}",
            record['course'],
            record['purpose'],
            record['lab_room'],
            record['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
            record['end_time'].strftime('%Y-%m-%d %H:%M:%S') if record['end_time'] else 'Active',
            record['duration_minutes']
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{filename}.csv"
    )

def export_excel(records, filename):
    # Prepare DataFrame
    data = []
    for record in records:
        data.append({
            'ID': record['id'],
            'Student ID': record['student_id'],
            'Student Name': f"{record['firstname']} {record['lastname']}",
            'Course': record['course'],
            'Purpose': record['purpose'],
            'Lab Room': record['lab_room'],
            'Start Time': record['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
            'End Time': record['end_time'].strftime('%Y-%m-%d %H:%M:%S') if record['end_time'] else 'Active',
            'Duration (minutes)': record['duration_minutes']
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sit-in Records', index=False)
        
        # Add some formatting
        workbook = writer.book
        worksheet = writer.sheets['Sit-in Records']
        
        # Format header
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#0047ab',
            'color': 'white',
            'border': 1
        })
        
        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, max(len(value) + 2, 15))
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"{filename}.xlsx"
    )

def export_pdf(records, filename):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Add title
    styles = getSampleStyleSheet()
    title = Paragraph(f"Sit-in Records - {datetime.now().strftime('%Y-%m-%d')}", styles['Title'])
    elements.append(title)
    
    # Prepare data for table
    table_data = [['ID', 'Student ID', 'Student Name', 'Course', 'Purpose', 'Lab Room', 'Start Time', 'End Time', 'Duration']]
    
    for record in records:
        table_data.append([
            str(record['id']),
            record['student_id'],
            f"{record['firstname']} {record['lastname']}",
            record['course'],
            record['purpose'],
            record['lab_room'],
            record['start_time'].strftime('%Y-%m-%d %H:%M'),
            record['end_time'].strftime('%Y-%m-%d %H:%M') if record['end_time'] else 'Active',
            f"{record['duration_minutes']} min"
        ])
    
    # Create the table
    table = Table(table_data)
    
    # Style the table
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])
    table.setStyle(style)
    
    # Add table to elements
    elements.append(table)
    
    # Build the PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{filename}.pdf"
    )

@app.route("/api/check_active_session")
def api_check_active_session():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    student_id = request.args.get("student_id", "")
    if not student_id:
        return jsonify({"error": "Student ID is required"}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check for active sit-in sessions
        cursor.execute("""
            SELECT id, lab_room, start_time
            FROM sit_ins
            WHERE student_id = %s AND end_time IS NULL
            LIMIT 1
        """, (student_id,))
        
        active_session = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if active_session:
            return jsonify({
                "active": True,
                "sit_in_id": active_session["id"],
                "lab_room": active_session["lab_room"],
                "start_time": active_session["start_time"].isoformat()
            })
        else:
            return jsonify({"active": False})
            
    except Error as e:
        return jsonify({"error": str(e)}), 500

# Debug endpoint to check students in database
@app.route("/api/debug/students")
def api_debug_students():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all students
        cursor.execute("SELECT idno, firstname, lastname, course, yearlevel FROM students LIMIT 20")
        students = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "students_count": len(students),
            "students": students
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/debug/search_student")
def api_debug_search_student():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    student_id = request.args.get("id", "")
    if not student_id:
        return jsonify({"error": "Student ID is required"}), 400
    
    # Clean up the student ID
    student_id = student_id.strip()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get database version
        cursor.execute("SELECT VERSION() as version")
        version = cursor.fetchone()
        
        # Get database character set
        cursor.execute("SHOW VARIABLES LIKE 'character_set_%'")
        charset_info = cursor.fetchall()
        
        # Get table structure
        cursor.execute("DESCRIBE students")
        table_structure = cursor.fetchall()
        
        # Try direct raw query
        cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
        exact_match_result = cursor.fetchone()
        
        # Try with different formats
        cursor.execute("SELECT * FROM students WHERE idno = %s", (str(student_id),))
        string_match_result = cursor.fetchone()
        
        # Try with leading zero padding
        padded_id = student_id.zfill(8)  # Pad to 8 digits
        cursor.execute("SELECT * FROM students WHERE idno = %s", (padded_id,))
        padded_match_result = cursor.fetchone()
        
        # Try as integer
        try:
            int_id = int(student_id)
            cursor.execute("SELECT * FROM students WHERE idno = %s", (int_id,))
            int_match_result = cursor.fetchone()
        except (ValueError, TypeError):
            int_match_result = None
            
        # Get all IDs from database for comparison
        cursor.execute("SELECT idno FROM students LIMIT 50")
        all_ids = [row['idno'] for row in cursor.fetchall()]
        
        # Find closest matching IDs
        close_matches = []
        for db_id in all_ids:
            if str(student_id) in str(db_id) or str(db_id) in str(student_id):
                close_matches.append(db_id)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "debug_info": {
                "searched_id": student_id,
                "id_type": str(type(student_id)),
                "database_version": version,
                "charset_info": charset_info,
                "students_table_structure": table_structure,
                "exact_match_found": exact_match_result is not None,
                "string_match_found": string_match_result is not None,
                "padded_match_found": padded_match_result is not None,
                "int_match_found": int_match_result is not None,
                "all_ids_sample": all_ids[:20],  # First 20 IDs
                "close_matches": close_matches
            }
        })
        
    except Error as e:
        error_message = str(e)
        traceback_info = traceback.format_exc()
        return jsonify({
            "error": error_message, 
            "traceback": traceback_info
        }), 500

@app.route("/api/debug/table_structure")
def api_debug_table_structure():
    if "admin" not in session:
        return jsonify({"error": "Admin login required"}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get table structure for relevant tables
        cursor.execute("SHOW COLUMNS FROM sit_ins")
        sit_ins_columns = cursor.fetchall()
        
        cursor.execute("SHOW COLUMNS FROM students")
        students_columns = cursor.fetchall()
        
        # Get a sample record from sit_ins if any exists
        cursor.execute("SELECT * FROM sit_ins LIMIT 1")
        sit_in_sample = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "sit_ins_columns": sit_ins_columns,
            "students_columns": students_columns,
            "sit_in_sample": sit_in_sample
        })
        
    except Error as e:
        error_message = str(e)
        traceback_info = traceback.format_exc()
        return jsonify({
            "error": error_message, 
            "traceback": traceback_info
        }), 500

@app.route("/student_reservation")
def student_reservation():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    if not student:
        flash("Student not found", "error")
        return redirect(url_for('home'))
    
    # Get current date and time for the form
    now = datetime.now()
    current_time = now.strftime("%I:%M %p")  # Format as 12-hour time with AM/PM
    current_date = now.strftime("%B %d, %Y")  # Format as Month Day, Year
    
    # Format date and time for form inputs
    current_time_24h = now.strftime("%H:%M")  # Format as 24-hour time for time input
    current_date_ymd = now.strftime("%Y-%m-%d")  # Format as YYYY-MM-DD for date input
    
    return render_template("student/reservation.html", 
                           user=student,
                           current_time=current_time,
                           current_date=current_date,
                           current_time_24h=current_time_24h,
                           current_date_ymd=current_date_ymd)

@app.route("/api/check_lab_availability")
def api_check_lab_availability():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    lab = request.args.get("lab", "")
    if not lab:
        return jsonify({"error": "Lab parameter is required"}), 400
    
    # In a real system, you would query a database to get real-time availability
    # For now, we'll simulate some availability data
    lab_capacities = {
        "524": 30,
        "526": 25,
        "528": 20,
        "530": 35,
        "542": 20,
        "544": 35
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Count active sit-ins for the selected lab
        cursor.execute("""
            SELECT COUNT(*) as active_count 
            FROM sit_ins 
            WHERE lab_room = %s AND end_time IS NULL
        """, (lab,))
        
        active_count = cursor.fetchone()['active_count']
        
        # Calculate available computers
        total_capacity = lab_capacities.get(lab, 0)
        available_computers = max(0, total_capacity - active_count)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "lab": lab,
            "total_capacity": total_capacity,
            "active_sessions": active_count,
            "available_computers": available_computers
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/check_student_active_sessions")
def api_check_student_active_sessions():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check for active sit-ins for this student that are approved (not pending)
        cursor.execute("""
            SELECT id FROM sit_ins 
            WHERE student_id = %s AND end_time IS NULL AND status = 'approved'
            LIMIT 1
        """, (student_id,))
        
        active_session = cursor.fetchone()
        
        # Also check if there are any pending reservations
        cursor.execute("""
            SELECT id FROM sit_ins 
            WHERE student_id = %s AND end_time IS NULL AND status = 'pending'
            LIMIT 1
        """, (student_id,))
        
        pending_reservation = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "has_active_session": active_session is not None,
            "has_pending_reservation": pending_reservation is not None,
            "session_id": active_session['id'] if active_session else None,
            "pending_id": pending_reservation['id'] if pending_reservation else None
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create_reservation", methods=["POST"])
def create_reservation():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    purpose = request.form.get("purpose")
    lab = request.form.get("lab")
    custom_time = request.form.get("time_in")
    custom_date = request.form.get("date")
    
    if not all([purpose, lab]):
        flash("Purpose and Laboratory are required fields", "error")
        return redirect(url_for('student_reservation'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if student exists
        cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            flash("Student not found", "error")
            return redirect(url_for('home'))
        
        # Check if student has active sit-in
        cursor.execute("""
            SELECT id FROM sit_ins 
            WHERE student_id = %s AND end_time IS NULL
            LIMIT 1
        """, (student_id,))
        
        if cursor.fetchone():
            flash("You already have an active lab session", "error")
            return redirect(url_for('student_dashboard'))
        
        # Check remaining sessions
        if student['remaining_sessions'] <= 0:
            flash("You have no remaining sessions left", "error")
            return redirect(url_for('student_dashboard'))
        
        # Check lab availability
        lab_capacities = {
            "524": 30,
            "526": 25,
            "528": 20,
            "530": 35,
            "542": 20,
            "544": 35
        }
        
        cursor.execute("""
            SELECT COUNT(*) as active_count 
            FROM sit_ins 
            WHERE lab_room = %s AND end_time IS NULL
        """, (lab,))
        
        active_count = cursor.fetchone()['active_count']
        total_capacity = lab_capacities.get(lab, 0)
        
        if active_count >= total_capacity:
            flash(f"No computers available in {lab}. Please select another lab.", "error")
            return redirect(url_for('student_reservation'))
        
        # Handle custom date and time if provided
        start_time = None
        
        if custom_date and custom_time:
            # Combine date and time into a datetime object
            start_time = datetime.strptime(f"{custom_date} {custom_time}", "%Y-%m-%d %H:%M")
        elif custom_date:
            # Use custom date with current time
            current_time = datetime.now().strftime("%H:%M")
            start_time = datetime.strptime(f"{custom_date} {current_time}", "%Y-%m-%d %H:%M")
        elif custom_time:
            # Use custom time with current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            start_time = datetime.strptime(f"{current_date} {custom_time}", "%Y-%m-%d %H:%M")
        
        # Create the reservation (sit-in)
        if start_time:
            cursor.execute("""
                INSERT INTO sit_ins (student_id, purpose, lab_room, start_time, created_by, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
            """, (student_id, purpose, lab, start_time, student_id))
        else:
            cursor.execute("""
                INSERT INTO sit_ins (student_id, purpose, lab_room, start_time, created_by, status)
                VALUES (%s, %s, %s, NOW(), %s, 'pending')
            """, (student_id, purpose, lab, student_id))
        
        # Get the ID of the newly created reservation
        sit_in_id = cursor.lastrowid
        
        # No need to update remaining sessions yet, will do that when approved
        
        # Create a notification for this reservation
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
            VALUES (%s, 'reservation', %s, %s, NOW(), 0)
        """, (
            student_id, 
            f"Your reservation request for {lab} has been submitted and is pending approval.", 
            sit_in_id
        ))
        
        conn.commit()
        
        # Set success message in session for popup
        session['reservation_success'] = True
        session['reservation_lab'] = lab
        session['reservation_purpose'] = purpose
        
        flash("Reservation request submitted! Waiting for admin approval.", "success")
        return redirect(url_for('student_dashboard', 
                              reservation_success=True, 
                              lab=lab, 
                              purpose=purpose))
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for('student_reservation'))
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/student_history")
def student_history():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get student info
        cursor.execute("SELECT * FROM students WHERE idno = %s", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            flash("Student not found", "error")
            return redirect(url_for('home'))
        
        # Get active session if exists (must be approved)
        cursor.execute("""
            SELECT * FROM sit_ins 
            WHERE student_id = %s AND end_time IS NULL AND status = 'approved'
            ORDER BY start_time DESC
            LIMIT 1
        """, (student_id,))
        active_session = cursor.fetchone()
        
        # Get pending reservations
        cursor.execute("""
            SELECT * FROM sit_ins 
            WHERE student_id = %s AND status = 'pending'
            ORDER BY start_time DESC
        """, (student_id,))
        pending_reservations = cursor.fetchall()
        
        # Get all session history
        cursor.execute("""
            SELECT * FROM sit_ins 
            WHERE student_id = %s
            ORDER BY start_time DESC
            LIMIT 50
        """, (student_id,))
        sessions = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template(
            "student/history.html",
            user=student,
            active_session=active_session,
            pending_reservations=pending_reservations,
            sessions=sessions
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for('student_dashboard'))

@app.route("/end_student_session/<int:session_id>", methods=["POST"])
def end_student_session(session_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "You must be logged in"})

    student_id = session["user_id"]

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if the session belongs to the logged-in student, is approved, and is not already ended
        cursor.execute(
            "SELECT * FROM sit_ins WHERE id = %s AND student_id = %s AND end_time IS NULL AND status = 'approved'",
            (session_id, student_id),
        )
        session_record = cursor.fetchone()

        if not session_record:
            conn.close()
            return jsonify({"success": False, "message": "Invalid session, session already ended, or session not yet approved"})

        # Update the end_time to current time
        cursor.execute(
            "UPDATE sit_ins SET end_time = NOW() WHERE id = %s",
            (session_id,),
        )
        
        # Deduct one session from the student's remaining sessions
        cursor.execute(
            "UPDATE students SET remaining_sessions = GREATEST(remaining_sessions - 1, 0) WHERE idno = %s",
            (student_id,),
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Session ended successfully. One session has been deducted from your remaining sessions."})
    except Error as e:
        print(e)
        return jsonify({"success": False, "message": "An error occurred while ending the session"})

@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "You must be logged in"})

    student_id = session["user_id"]
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        subject = data.get('subject')
        message = data.get('message')
        
        if not session_id or not subject or not message:
            return jsonify({"success": False, "message": "Missing required fields"})
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if the session belongs to the logged-in student
        cursor.execute(
            "SELECT * FROM sit_ins WHERE id = %s AND student_id = %s",
            (session_id, student_id),
        )
        session_record = cursor.fetchone()
        
        if not session_record:
            conn.close()
            return jsonify({"success": False, "message": "Invalid session"})
        
        # Insert feedback into database
        cursor.execute(
            "INSERT INTO feedback (session_id, student_id, subject, message, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (session_id, student_id, subject, message),
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Feedback submitted successfully"})
    except Error as e:
        print(e)
        return jsonify({"success": False, "message": "An error occurred while submitting feedback"})

@app.route("/api/get_notifications")
def api_get_notifications():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get unread notifications
        cursor.execute("""
            SELECT id, type, message, created_at, is_read, reference_id
            FROM notifications
            WHERE student_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (student_id,))
        
        notifications = cursor.fetchall()
        
        # Count unread notifications
        cursor.execute("""
            SELECT COUNT(*) as unread_count
            FROM notifications
            WHERE student_id = %s AND is_read = 0
        """, (student_id,))
        
        unread_count = cursor.fetchone()['unread_count']
        
        cursor.close()
        conn.close()
        
        # Format timestamps
        for notification in notifications:
            if isinstance(notification['created_at'], datetime):
                notification['created_at'] = notification['created_at'].strftime("%b %d, %Y %I:%M %p")
        
        return jsonify({
            "notifications": notifications,
            "unread_count": unread_count
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/mark_notification_read/<int:notification_id>", methods=["POST"])
def api_mark_notification_read(notification_id):
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s AND student_id = %s
        """, (notification_id, student_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True})
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/mark_all_notifications_read", methods=["POST"])
def api_mark_all_notifications_read():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE student_id = %s
        """, (student_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True})
        
    except Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/clear_reservation_success", methods=["POST"])
def api_clear_reservation_success():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401
    
    # Clear reservation success session variables
    if 'reservation_success' in session:
        session.pop('reservation_success')
    if 'reservation_lab' in session:
        session.pop('reservation_lab')
    if 'reservation_purpose' in session:
        session.pop('reservation_purpose')
    
    return jsonify({"success": True})

@app.route("/debug/create_test_notification", methods=["GET"])
def debug_create_test_notification():
    if 'user_id' not in session:
        flash("You need to log in first", "error")
        return redirect(url_for('home'))
    
    student_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create a test notification
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, created_at, is_read)
            VALUES (%s, 'test', 'This is a test notification to verify the notification system is working properly.', NOW(), 0)
        """, (student_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Test notification created successfully!", "success")
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for('student_dashboard'))

@app.route("/admin_reservation_requests")
def admin_reservation_requests():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    # Get page number and records per page
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Get filter parameters
    student_id = request.args.get('student_id', '')
    course = request.args.get('course', '')
    lab_room = request.args.get('lab_room', '')
    status = request.args.get('status', 'pending')  # Default to pending
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build query with filters
        query = """
            SELECT s.id, s.student_id, u.firstname, u.lastname, u.course, u.yearlevel, 
                   s.purpose, s.lab_room, s.start_time, s.status, s.admin_notes, 
                   u.remaining_sessions
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) as total FROM sit_ins s JOIN students u ON s.student_id = u.idno WHERE 1=1"
        params = []
        
        if student_id:
            query += " AND s.student_id = %s"
            count_query += " AND s.student_id = %s"
            params.append(student_id)
        
        if course:
            query += " AND u.course = %s"
            count_query += " AND u.course = %s"
            params.append(course)
        
        if lab_room:
            query += " AND s.lab_room = %s"
            count_query += " AND s.lab_room = %s"
            params.append(lab_room)
        
        if status:
            query += " AND s.status = %s"
            count_query += " AND s.status = %s"
            params.append(status)
        
        # Add ordering and pagination
        query += " ORDER BY s.start_time DESC LIMIT %s OFFSET %s"
        offset = (page - 1) * per_page
        
        # Get total record count
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page  # Ceiling division
        
        # Execute query with pagination parameters
        cursor.execute(query, params + [per_page, offset])
        reservations = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/reservation_requests.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            reservations=reservations,
            page=page,
            total_pages=total_pages,
            filters={
                'student_id': student_id,
                'course': course,
                'lab_room': lab_room,
                'status': status
            }
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template(
            "admin/reservation_requests.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            reservations=[],
            page=1,
            total_pages=0,
            filters={
                'student_id': '',
                'course': '',
                'lab_room': '',
                'status': 'pending'
            }
        )

@app.route("/admin_approve_reservation/<int:reservation_id>", methods=["POST"])
def admin_approve_reservation(reservation_id):
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    admin_notes = request.form.get("admin_notes", "")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if reservation exists and is pending
        cursor.execute("""
            SELECT s.id, s.student_id, s.status
            FROM sit_ins s
            WHERE s.id = %s
        """, (reservation_id,))
        
        reservation = cursor.fetchone()
        
        if not reservation:
            flash("Reservation not found", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        if reservation['status'] != 'pending':
            flash("Only pending reservations can be approved", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        # Update reservation status to approved
        cursor.execute("""
            UPDATE sit_ins 
            SET status = 'approved', admin_notes = %s
            WHERE id = %s
        """, (admin_notes, reservation_id))
        
        # Create notification for the student
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
            VALUES (%s, 'reservation', %s, %s, NOW(), 0)
        """, (
            reservation['student_id'], 
            f"Your reservation request has been approved. Sessions will be deducted when you end your session. {admin_notes if admin_notes else ''}",
            reservation_id
        ))
        
        conn.commit()
        flash(f"Reservation #{reservation_id} has been approved", "success")
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for("admin_reservation_requests"))

@app.route("/admin_deny_reservation/<int:reservation_id>", methods=["POST"])
def admin_deny_reservation(reservation_id):
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    admin_notes = request.form.get("admin_notes", "")
    if not admin_notes:
        flash("Please provide a reason for denying the reservation", "error")
        return redirect(url_for("admin_reservation_requests"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if reservation exists and is pending
        cursor.execute("""
            SELECT s.id, s.student_id, s.status
            FROM sit_ins s
            WHERE s.id = %s
        """, (reservation_id,))
        
        reservation = cursor.fetchone()
        
        if not reservation:
            flash("Reservation not found", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        if reservation['status'] != 'pending':
            flash("Only pending reservations can be denied", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        # Update reservation status to rejected
        cursor.execute("""
            UPDATE sit_ins 
            SET status = 'rejected', admin_notes = %s
            WHERE id = %s
        """, (admin_notes, reservation_id))
        
        # Create notification for the student
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
            VALUES (%s, 'reservation', %s, %s, NOW(), 0)
        """, (
            reservation['student_id'], 
            f"Your reservation request has been denied. Reason: {admin_notes}",
            reservation_id
        ))
        
        conn.commit()
        flash(f"Reservation #{reservation_id} has been denied", "success")
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for("admin_reservation_requests"))

@app.route("/admin_end_session/<int:sit_in_id>", methods=["POST"])
def admin_end_session(sit_in_id):
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if the sit-in exists and is active
        cursor.execute("""
            SELECT s.id, s.student_id, s.status, s.end_time
            FROM sit_ins s
            WHERE s.id = %s
        """, (sit_in_id,))
        
        sit_in = cursor.fetchone()
        
        if not sit_in:
            flash("Session not found", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        if sit_in['status'] != 'approved':
            flash("Only approved reservations can be ended", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        if sit_in['end_time'] is not None:
            flash("This session has already ended", "error")
            return redirect(url_for("admin_reservation_requests"))
        
        # End the session
        cursor.execute("""
            UPDATE sit_ins 
            SET end_time = NOW()
            WHERE id = %s
        """, (sit_in_id,))
        
        # Deduct one session from the student's remaining sessions
        cursor.execute("""
            UPDATE students
            SET remaining_sessions = GREATEST(remaining_sessions - 1, 0)
            WHERE idno = %s
        """, (sit_in['student_id'],))
        
        # Create notification for the student
        cursor.execute("""
            INSERT INTO notifications (student_id, type, message, reference_id, created_at, is_read)
            VALUES (%s, 'reservation', %s, %s, NOW(), 0)
        """, (
            sit_in['student_id'], 
            f"Your lab session has been ended by an administrator. One session has been deducted from your remaining sessions.",
            sit_in_id
        ))
        
        conn.commit()
        flash(f"Session #{sit_in_id} has been ended and session count deducted", "success")
        
    except Error as e:
        flash(f"Database error: {e}", "error")
    
    return redirect(url_for("admin_reservation_requests"))

@app.route("/admin_students")
def admin_students():
    if "admin" not in session:
        flash("Please login as admin first.", "error")
        return redirect(url_for("home"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all students
        cursor.execute("""
            SELECT * FROM students 
            ORDER BY lastname, firstname
        """)
        students = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/students.html",
            admin=ADMIN_CREDENTIALS[session["admin"]],
            students=students
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template(
            "admin/students.html",
            admin=ADMIN_CREDENTIALS[session["admin"]],
            students=[]
        )

@app.route("/admin_add_student", methods=["POST"])
def admin_add_student():
    if "admin" not in session:
        flash("Please login as admin first.", "error")
        return redirect(url_for("home"))
    
    try:
        # Get form data
        firstname = request.form.get("firstname")
        lastname = request.form.get("lastname")
        student_id = request.form.get("student_id")
        email = request.form.get("email")
        course = request.form.get("course")
        yearlevel = request.form.get("yearlevel")
        contact = request.form.get("contact")
        password = request.form.get("password")
        
        # Validate required fields
        if not all([firstname, lastname, student_id, email, course, yearlevel, contact, password]):
            flash("All fields are required.", "error")
            return redirect(url_for("admin_students"))
        
        # Hash password
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if student ID already exists
        cursor.execute("SELECT id FROM students WHERE student_id = %s", (student_id,))
        if cursor.fetchone():
            flash("Student ID already exists.", "error")
            return redirect(url_for("admin_students"))
        
        # Insert new student
        cursor.execute("""
            INSERT INTO students (
                firstname, lastname, student_id, email, course, 
                yearlevel, contact, password, is_active, remaining_sessions
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            firstname, lastname, student_id, email, course,
            yearlevel, contact, hashed_password, True, 0
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Student added successfully!", "success")
        return redirect(url_for("admin_students"))
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("admin_students"))

@app.route("/admin_toggle_student_status/<int:student_id>", methods=["POST"])
def admin_toggle_student_status(student_id):
    if "admin" not in session:
        return jsonify({"success": False, "message": "Please login as admin first."})
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current status
        cursor.execute("SELECT is_active FROM students WHERE id = %s", (student_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"success": False, "message": "Student not found."})
        
        # Toggle status
        new_status = not result[0]
        cursor.execute("""
            UPDATE students 
            SET is_active = %s 
            WHERE id = %s
        """, (new_status, student_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": f"Student {'activated' if new_status else 'deactivated'} successfully!",
            "new_status": new_status
        })
        
    except Error as e:
        return jsonify({"success": False, "message": f"Database error: {e}"})

@app.route("/admin_reset_student_password/<int:student_id>", methods=["POST"])
def admin_reset_student_password(student_id):
    if "admin" not in session:
        return jsonify({"success": False, "message": "Please login as admin first."})
    
    try:
        # Generate a random password
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        hashed_password = generate_password_hash(new_password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update password
        cursor.execute("""
            UPDATE students 
            SET password = %s 
            WHERE id = %s
        """, (hashed_password, student_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Password reset successfully!",
            "new_password": new_password
        })
        
    except Error as e:
        return jsonify({"success": False, "message": f"Database error: {e}"})

@app.route("/admin_active_sit_ins")
def admin_active_sit_ins():
    if "admin" not in session:
        flash("Admin login required", "error")
        return redirect(url_for("home"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all active sit-in sessions with student details
        cursor.execute("""
            SELECT s.id, s.student_id, u.firstname, u.lastname, u.course, s.purpose, 
                   s.lab_room, s.start_time, TIMESTAMPDIFF(MINUTE, s.start_time, NOW()) as duration
            FROM sit_ins s
            JOIN students u ON s.student_id = u.idno
            WHERE s.end_time IS NULL
            ORDER BY s.start_time DESC
        """)
        active_sit_ins = cursor.fetchall()
        
        # Count BSIT/BSCS students
        cs_students = sum(1 for sit_in in active_sit_ins if sit_in['course'] in ['BSIT', 'BSCS'])
        
        # Count other students
        other_students = len(active_sit_ins) - cs_students
        
        # Determine most used lab
        if active_sit_ins:
            lab_counts = {}
            for sit_in in active_sit_ins:
                lab_room = sit_in['lab_room']
                lab_counts[lab_room] = lab_counts.get(lab_room, 0) + 1
            
            most_used_lab = max(lab_counts.items(), key=lambda x: x[1])[0] if lab_counts else "N/A"
        else:
            most_used_lab = "N/A"
        
        cursor.close()
        conn.close()
        
        return render_template(
            "admin/active_sit_ins.html", 
            admin=ADMIN_CREDENTIALS[session["admin"]],
            active_sit_ins=active_sit_ins,
            cs_students=cs_students,
            other_students=other_students,
            most_used_lab=most_used_lab
        )
        
    except Error as e:
        flash(f"Database error: {e}", "error")
        return render_template("admin/active_sit_ins.html", admin=ADMIN_CREDENTIALS[session["admin"]])

if __name__ == "__main__":
    app.run(debug=True)
