import os
import re
import io
import uuid
import zipfile
import sqlite3
import secrets
import requests
from flask import Flask, render_template, request, redirect, session, send_from_directory, send_file, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)

# --- Güvenlik / Ayarlar -----------------------------------------------
# Ortam değişkeni yoksa geliştirme için rastgele bir key üretilir.
# Render'da SECRET_KEY, ADMIN_USER, ADMIN_PASS mutlaka ortam değişkeni olarak set edilmeli.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "1234")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER", "") != ""  # Render'da https zorunlu
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # istek başı toplam 100MB

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

DB_PATH = os.path.join(UPLOAD_FOLDER, "photos.db")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic", "heif"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                guest_name TEXT,
                guest_message TEXT,
                uploaded_at TEXT NOT NULL
            )
        """)
        # Eski veritabanlarında guest_message sütunu yoksa ekle (geriye dönük uyumluluk)
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(photos)")}
        if "guest_message" not in existing_cols:
            conn.execute("ALTER TABLE photos ADD COLUMN guest_message TEXT")


init_db()


def clean_guest_name(raw_name):
    """Görünen ismi temizler: kontrol karakterlerini kaldırır, uzunluğu sınırlar.
    (secure_filename KULLANILMAZ çünkü bu bir dosya adı değil, ekranda gösterilecek bir isimdir —
    Türkçe karakterleri ve boşlukları bozar.)"""
    name = raw_name.strip()
    name = re.sub(r"[\r\n\t]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name[:60]


def clean_guest_message(raw_message):
    """Kutlama mesajını temizler: satır sonlarını korur ama uzunluğu sınırlar."""
    message = raw_message.strip()
    message = re.sub(r"\r\n", "\n", message)
    return message[:300]

# --- Telegram Bot -------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def telegram_enabled():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_to_telegram(filepath, filename, guest_name="", guest_message=""):
    """Fotoğrafı Telegram'a 'document' olarak gönderir (kalite kaybı olmadan)."""
    if not telegram_enabled():
        return False, "Telegram yapılandırılmamış"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    caption = f"📸 Yeni fotoğraf: {guest_name}" if guest_name else "📸 Yeni fotoğraf yüklendi"
    if guest_message:
        caption += f"\n💌 {guest_message}"

    try:
        with open(filepath, "rb") as f:
            response = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1024]},
                files={"document": (filename, f)},
                timeout=30,
            )
        if response.ok:
            return True, "OK"
        return False, response.text
    except requests.RequestException as exc:
        return False, str(exc)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(413)
def too_large(e):
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({
        "success": False,
        "message": f"Fotoğraflar çok büyük (limit: {max_mb}MB). Daha az fotoğraf seçip tekrar deneyin."
    }), 413


# --- Routes --------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "files" not in request.files:
        return jsonify({"success": False, "message": "Dosya bulunamadı"}), 400

    files = request.files.getlist("files")
    guest_name = clean_guest_name(request.form.get("name", ""))
    guest_message = clean_guest_message(request.form.get("message", ""))

    if not files or all(f.filename == "" for f in files):
        return jsonify({"success": False, "message": "Lütfen fotoğraf seçin"}), 400

    saved_count = 0
    errors = []

    with get_db() as conn:
        for file in files:
            if file.filename == "":
                continue

            if not allowed_file(file.filename):
                errors.append(f"{file.filename}: desteklenmeyen dosya türü")
                continue

            ext = file.filename.rsplit(".", 1)[1].lower()
            time_prefix = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_name = f"{time_prefix}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

            file.save(filepath)
            saved_count += 1

            conn.execute(
                "INSERT INTO photos (filename, guest_name, guest_message, uploaded_at) VALUES (?, ?, ?, ?)",
                (unique_name, guest_name, guest_message, datetime.now().isoformat()),
            )

            # Telegram'a orijinal kalitede belge olarak gönder
            if telegram_enabled():
                send_to_telegram(filepath, unique_name, guest_name, guest_message)

    if saved_count == 0:
        return jsonify({"success": False, "message": "Hiçbir fotoğraf yüklenemedi", "errors": errors}), 400

    return jsonify({"success": True, "count": saved_count, "errors": errors})


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if secrets.compare_digest(username, ADMIN_USER) and secrets.compare_digest(password, ADMIN_PASS):
            session["admin"] = True
            return redirect("/panel")

        return render_template("admin_login.html", error="Hatalı kullanıcı adı veya şifre")

    return render_template("admin_login.html")


@app.route("/panel")
def panel():
    if not session.get("admin"):
        return redirect("/admin")

    disk_files = set(os.listdir(app.config["UPLOAD_FOLDER"]))

    with get_db() as conn:
        rows = conn.execute(
            "SELECT filename, guest_name, guest_message, uploaded_at FROM photos ORDER BY uploaded_at DESC"
        ).fetchall()

    photos = []
    known_files = set()
    for row in rows:
        if row["filename"] in disk_files and allowed_file(row["filename"]):
            photos.append({
                "filename": row["filename"],
                "guest_name": row["guest_name"] or "",
                "guest_message": row["guest_message"] or "",
                "uploaded_at": row["uploaded_at"],
            })
            known_files.add(row["filename"])

    # Veritabanında kaydı olmayan ama diskte duran eski dosyalar varsa (örn. eski sürümden kalan)
    # yine de listeye ekle, sadece isim bilgisi olmadan.
    for f in sorted(disk_files - known_files, reverse=True):
        if allowed_file(f):
            photos.append({"filename": f, "guest_name": "", "guest_message": "", "uploaded_at": ""})

    return render_template("admin.html", photos=photos)


@app.route("/panel/download-all")
def download_all():
    if not session.get("admin"):
        return redirect("/admin")

    disk_files = sorted(f for f in os.listdir(app.config["UPLOAD_FOLDER"]) if allowed_file(f))
    if not disk_files:
        return redirect("/panel")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in disk_files:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            zf.write(filepath, arcname=filename)
    buffer.seek(0)

    zip_name = f"selenay-ahmet-fotograflar-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@app.route("/panel/delete/<path:filename>", methods=["POST"])
def delete_photo(filename):
    if not session.get("admin"):
        return redirect("/admin")

    safe_name = secure_filename(filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)

    if os.path.exists(filepath) and allowed_file(safe_name):
        os.remove(filepath)

    with get_db() as conn:
        conn.execute("DELETE FROM photos WHERE filename = ?", (safe_name,))

    return redirect("/panel")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if not session.get("admin"):
        return redirect("/admin")
    safe_name = secure_filename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/admin")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
