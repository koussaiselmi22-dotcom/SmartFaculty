from flask import Flask, render_template, request, session, redirect, abort, flash  # FIX: added flash
from werkzeug.utils import secure_filename
import mysql.connector
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = "smartfaculty"
app.config["UPLOAD_FOLDER"] = "static/uploads"


# =========================
# DB CONNECTION
# =========================
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="SmartFaculty"
    )


# =========================
# ROLE HELPERS
# =========================
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect("/login")
            role = session.get("role")
            if role == "admin":
                return fn(*args, **kwargs)
            if role not in roles:
                return abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return render_template("home.html")


# =========================
# REGISTER
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        db.close()
        flash("Email already registered ❌", "danger")  # FIX: was returning plain string
        return redirect("/register")

    cursor.execute(
        "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
        (name, email, password, "user")
    )
    user_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO student_cards (user_id, level) VALUES (%s, %s)",
        (user_id, "L1")
    )

    db.commit()
    db.close()
    return redirect("/login")


# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (email, password)
    )
    user = cursor.fetchone()
    db.close()

    if user:
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]
        return redirect("/dashboard")  # FIX: tous les rôles → /dashboard (professor_dashboard.html n'existe pas)

    flash("Invalid email or password ❌", "danger")  # FIX: was returning plain string
    return redirect("/login")


# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM rooms")
    rooms_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM room_access")
    access_count = cursor.fetchone()[0]

    db.close()

    return render_template(
        "dashboard.html",
        name=session["name"],
        role=session["role"],
        users_count=users_count,
        rooms_count=rooms_count,
        access_count=access_count
    )


# FIX: removed professor_dashboard route — template n'existait pas → 500 error


# =========================
# MY ROOMS  ← FIX: route manquante (lien existe dans dashboard.html)
# =========================
@app.route("/my_rooms")
@login_required
def my_rooms():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.* FROM rooms r
        INNER JOIN room_access ra ON ra.room_id = r.id
        WHERE ra.user_id = %s
    """, (session["user_id"],))
    rooms = cursor.fetchall()
    db.close()
    return render_template("rooms.html", rooms=rooms)


# =========================
# ROOMS LIST
# =========================
@app.route("/rooms")
@login_required
def rooms():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rooms")
    rooms = cursor.fetchall()
    db.close()
    return render_template("rooms.html", rooms=rooms)


# =========================
# ADD ROOM (ADMIN ONLY)
# =========================
@app.route("/rooms/add", methods=["GET", "POST"])
@role_required("admin",)
def add_room():
    if request.method == "POST":
        name = request.form["name"]
        level = request.form["level"]
        description = request.form["description"]

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO rooms (name, level, description) VALUES (%s, %s, %s)",
            (name, level, description)
        )
        db.commit()
        db.close()
        return redirect("/rooms")

    return render_template("add_room.html")


# =========================
# EDIT ROOM (ADMIN ONLY)
# =========================
@app.route("/rooms/edit/<int:id>", methods=["GET", "POST"])
@role_required("admin")
def edit_room(id):
    db = get_db()

    if request.method == "POST":
        name = request.form["name"]
        level = request.form["level"]
        description = request.form["description"]

        # FIX: cursor yintaamel mara wehda — avant kan yitsenna cursor(dictionary=True)
        # mba3d yibdel b cursor() akhour → resource leak w code confus
        cursor = db.cursor()
        cursor.execute(
            "UPDATE rooms SET name=%s, level=%s, description=%s WHERE id=%s",
            (name, level, description, id)
        )
        db.commit()
        db.close()
        return redirect("/rooms")

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rooms WHERE id=%s", (id,))
    room = cursor.fetchone()
    db.close()
    return render_template("edit_room.html", room=room)


# =========================
# DELETE ROOM (ADMIN ONLY)
# =========================
@app.route("/rooms/delete/<int:id>")
@role_required("admin")
def delete_room(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM rooms WHERE id=%s", (id,))
    db.commit()
    db.close()
    return redirect("/rooms")


# =========================
# USERS LIST (ADMIN ONLY)
# =========================
@app.route("/users")
@role_required("admin")
def users():
    search = request.args.get("search", "")
    role_filter = request.args.get("role", "")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = "SELECT id, name, email, role FROM users WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE %s OR email LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    if role_filter:
        query += " AND role=%s"
        params.append(role_filter)

    cursor.execute(query, params)
    users = cursor.fetchall()
    db.close()

    return render_template("users.html", users=users)


# =========================
# CHANGE ROLE (ADMIN ONLY)
# =========================
@app.route("/users/change_role/<int:user_id>", methods=["POST"])
@role_required("admin")
def change_role(user_id):
    new_role = request.form.get("role")

    if new_role not in ["user", "professor", "admin", "moderator"]:
        flash("Invalid role ❌", "danger")
        return redirect("/users")

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE users SET role=%s WHERE id=%s",
        (new_role, user_id)
    )
    db.commit()
    db.close()
    return redirect("/users")


# =========================
# OPEN ROOM
# =========================
@app.route("/room/<int:room_id>")
@login_required
def open_room(room_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
    room = cursor.fetchone()

    if not room:
        db.close()
        return "Room not found ❌", 404

    # FIX: admin w professor ma3andhomch restrictions — avant admin ki yidkhol room
    # ma3andhach student_card → yitblock b "No card ❌"
    role = session.get("role")
    if role not in ("admin", "professor"):
        cursor.execute(
            "SELECT * FROM student_cards WHERE user_id=%s",
            (session["user_id"],)
        )
        card = cursor.fetchone()

        cursor.execute(
            "SELECT * FROM room_access WHERE user_id=%s AND room_id=%s",
            (session["user_id"], room_id)
        )
        access = cursor.fetchone()

        if not card:
            db.close()
            return "No student card ❌", 403

        if card["level"] != room["level"]:
            # نتحقق إذا كان الطالب سبق وتحقق من قبل لهذه الغرفة
            cursor.execute(
                "SELECT * FROM card_verifications WHERE user_id=%s AND room_id=%s AND verified=1",
                (session["user_id"], room_id)
            )
            verified = cursor.fetchone()
            if not verified:
                db.close()
                return redirect(f"/verify_card/{room_id}")
        
        if not access:
            db.close()
            return new_func()

    cursor.execute("SELECT * FROM room_content WHERE room_id=%s", (room_id,))
    contents = cursor.fetchall()
    db.close()

    return render_template("room.html", room=room, contents=contents)

def new_func():
    return "Access denied ❌", 403


# =========================
# ADD CONTENT (PROFESSOR ONLY)
# =========================
@app.route("/room/<int:room_id>/add", methods=["GET", "POST"])
@role_required("professor")
def add_content(room_id):
    if request.method == "POST":
        title = request.form["title"]
        ctype = request.form["type"]
        content = request.form["content"]

        file = request.files["file"]
        filename = None

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO room_content (room_id, type, title, content, file_path)
            VALUES (%s, %s, %s, %s, %s)
        """, (room_id, ctype, title, content, filename))
        db.commit()
        db.close()
        return redirect(f"/room/{room_id}")

    return render_template("add_content.html", room_id=room_id)

@app.route("/verify_card/<int:room_id>", methods=["GET", "POST"])
@login_required
def verify_card(room_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # نتحقق من وجود الغرفة
    cursor.execute("SELECT * FROM rooms WHERE id=%s", (room_id,))
    room = cursor.fetchone()
    if not room:
        db.close()
        return "Room not found", 404
    
    if request.method == "POST":
        # نستقبل المستوى المستخرج من الـ OCR
        extracted_level = request.form.get("extracted_level")
        if not extracted_level:
            return "No level extracted", 400
        
        # نقارن مع مستوى الغرفة
        if extracted_level != room["level"]:
            return f"Level mismatch: your card shows {extracted_level}, but room requires {room['level']}", 403
        
        # نضيف التحقق الناجح في قاعدة البيانات
        cursor.execute(
            "INSERT INTO card_verifications (user_id, room_id, verified, verified_level) VALUES (%s, %s, 1, %s)",
            (session["user_id"], room_id, extracted_level)
        )
        db.commit()
        db.close()
        return "Verified ✅", 200
    
    db.close()
    return render_template("verify_card.html", room_id=room_id)

# =========================
# SCHEDULE MANAGEMENT (Admin + Moderator)
# =========================

@app.route("/schedule")
@login_required
def schedule():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # نجيب كل الحصص مع اسم الغرفة
    cursor.execute("""
        SELECT s.*, r.name as room_name 
        FROM schedule s
        JOIN rooms r ON r.id = s.room_id
        ORDER BY FIELD(s.day, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), s.start_time
    """)
    schedule = cursor.fetchall()
    db.close()
    
    return render_template("schedule.html", schedule=schedule)


@app.route("/schedule/add", methods=["GET", "POST"])
@login_required
def add_schedule():
    if session.get("role") not in ["admin", "moderator"]:
        abort(403)
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # نجيب الغرف باش نعرضهم في القائمة المنسدلة
    cursor.execute("SELECT id, name, level FROM rooms")
    rooms = cursor.fetchall()
    
    if request.method == "POST":
        room_id = request.form["room_id"]
        day = request.form["day"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        course_name = request.form["course_name"]
        professor_name = request.form.get("professor_name", "")
        
        cursor.execute("""
            INSERT INTO schedule (room_id, day, start_time, end_time, course_name, professor_name)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (room_id, day, start_time, end_time, course_name, professor_name))
        db.commit()
        db.close()
        flash("✅ Class added to schedule!", "success")
        return redirect("/schedule")
    
    db.close()
    return render_template("add_schedule.html", rooms=rooms)


@app.route("/schedule/edit/<int:schedule_id>", methods=["GET", "POST"])
@login_required
def edit_schedule(schedule_id):
    if session.get("role") not in ["admin", "moderator"]:
        abort(403)
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == "POST":
        room_id = request.form["room_id"]
        day = request.form["day"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        course_name = request.form["course_name"]
        professor_name = request.form.get("professor_name", "")
        
        cursor.execute("""
            UPDATE schedule 
            SET room_id=%s, day=%s, start_time=%s, end_time=%s, course_name=%s, professor_name=%s
            WHERE id=%s
        """, (room_id, day, start_time, end_time, course_name, professor_name, schedule_id))
        db.commit()
        db.close()
        flash("✅ Schedule updated!", "success")
        return redirect("/schedule")
    
    # نجيب بيانات الحصة
    cursor.execute("SELECT * FROM schedule WHERE id=%s", (schedule_id,))
    schedule_item = cursor.fetchone()
    
    # نجيب الغرف
    cursor.execute("SELECT id, name, level FROM rooms")
    rooms = cursor.fetchall()
    
    db.close()
    
    if not schedule_item:
        abort(404)
    
    return render_template("edit_schedule.html", schedule=schedule_item, rooms=rooms)


@app.route("/schedule/delete/<int:schedule_id>")
@login_required
def delete_schedule(schedule_id):
    if session.get("role") not in ["admin", "moderator"]:
        abort(403)
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM schedule WHERE id=%s", (schedule_id,))
    db.commit()
    db.close()
    flash("🗑️ Class removed from schedule!", "warning")
    return redirect("/schedule")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)