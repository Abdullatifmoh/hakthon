from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
import os
import json
import sqlite3
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
from html import escape

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://abdullatifmoh.github.io",
                "http://localhost:5000",
                "http://127.0.0.1:5000"
            ]
        }
    }
)

# =========================================================
# GEMINI
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# =========================================================
# EMAIL / NEWSLETTER SETTINGS
# =========================================================

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
ADMIN_TOKEN = os.environ.get("NEWSLETTER_ADMIN_TOKEN", "change-this-token")

# Local development: SQLite.
# For production on Render, point this to a persistent disk path or use a managed DB.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "tourism_investment.db")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# =========================================================
# DATABASE
# =========================================================

def db_connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'investor',
            newsletter_enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            week_label TEXT NOT NULL,
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id INTEGER,
            user_id INTEGER,
            email TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            sent_at TEXT NOT NULL,
            FOREIGN KEY(issue_id) REFERENCES newsletter_issues(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()

# =========================================================
# PLATFORM KNOWLEDGE BASE
# =========================================================

KNOWLEDGE_BASE = {
    "المشاريع": {
        "واحة أبها الترفيهية": {
            "location": "أبها، عسير",
            "sector": "ترفيه موسمي",
            "target": 50000,
            "raised": 38000,
            "shares": 50,
            "price": 1000,
            "risk": "منخفض",
            "attractiveness": "متوسطة",
            "financialCheck": "مكتمل",
            "budget": 50000,
            "actual": 38000,
            "guide": "المرشد خالد المالكي",
            "analysis": "الموقع استراتيجي والطلب السياحي مناسب، مع بقاء جزء من الميزانية غير مصروف."
        },
        "مخيم نجوم العلا": {
            "location": "العلا، المدينة المنورة",
            "sector": "ضيافة وإقامة",
            "target": 120000,
            "raised": 64200,
            "shares": 120,
            "price": 1000,
            "risk": "منخفض",
            "attractiveness": "عالية",
            "financialCheck": "مكتمل",
            "budget": 120000,
            "actual": 64200,
            "guide": "المرشدة سارة الحربي",
            "analysis": "وجهة سياحية قوية، والتمويل الحالي أقل من الميزانية المستهدفة."
        },
        "جولات كورنيش جدة": {
            "location": "جدة، مكة المكرمة",
            "sector": "جولات وفعاليات",
            "target": 80000,
            "raised": 80000,
            "shares": 80,
            "price": 1000,
            "risk": "منخفض",
            "attractiveness": "متوسطة",
            "financialCheck": "مكتمل",
            "budget": 80000,
            "actual": 80000,
            "guide": "المرشد عمر الزهراني",
            "analysis": "تم تمويل المشروع بالكامل وفق البيانات الحالية، مع إمكانية التوسع."
        },
        "واحة الأحساء التراثية": {
            "location": "الأحساء، المنطقة الشرقية",
            "sector": "ترفيه موسمي",
            "target": 90000,
            "raised": 42000,
            "shares": 90,
            "price": 1000,
            "risk": "متوسط",
            "attractiveness": "متوسطة",
            "financialCheck": "مكتمل",
            "budget": 90000,
            "actual": 42000,
            "guide": "المرشد عبدالرحمن الحربي",
            "analysis": "المشروع يجمع بين التراث والترفيه ويحتاج إلى تسويق قوي."
        }
    },
    "المخاطر": {
        "types": ["الموسمية", "التنافسية", "التغيرات التنظيمية", "العوامل الخارجية"],
        "advice": "نوّع استثماراتك، اختر مناطق مستقرة، ادرس الجدوى المالية، واستشر خبيراً."
    },
    "العوائد": {
        "average": "8-15% سنوياً",
        "factors": ["موقع المشروع", "جودة الخدمات", "استراتيجية التسويق", "إدارة التكاليف"]
    },
    "الملكية": {
        "formula": "نسبة الملكية = (عدد الأسهم / إجمالي الأسهم) × 100",
        "rights": ["أرباح سنوية", "تقارير مالية", "التصويت", "الاجتماعات"]
    }
}


def get_knowledge_context():
    return json.dumps(KNOWLEDGE_BASE, ensure_ascii=False, indent=2)

# =========================================================
# AI
# =========================================================

SYSTEM_PROMPT = """
أنت المستشار الذكي داخل منصة سعودية للاستثمار في المشاريع السياحية.
تحدث بالعربية وبأسلوب واضح واحترافي وبسيط.

القواعد:
- لا تخترع بيانات عن المشاريع.
- استخدم قاعدة البيانات الموجودة.
- إذا لم توجد المعلومة، قل إنها غير متوفرة.
- لا تخترع نسب عوائد جديدة.
- لا تستخدم مؤشر ثقة أو نسبة مئوية عشوائية.
- عند تحليل المشروع استخدم: مستوى المخاطر، جاذبية الاستثمار، وحالة الفحص المالي.
- عند الحديث عن Budget vs Actual اعرض الأرقام والانحراف والحالة.
- لا تدّعي أنك مستشار مالي مرخص.
- القرار الاستثماري النهائي للمستخدم.
- الاستثمار يحمل مخاطر.
- استخدم الريال السعودي.
"""


def generate_ai_response(user_message, conversation_history=None):
    if not GEMINI_API_KEY or client is None:
        return "⚠️ مفتاح Gemini API غير موجود أو لم يتم تشغيل المستشار الذكي."

    prompt = SYSTEM_PROMPT
    prompt += "\n\nبيانات المنصة:\n" + get_knowledge_context()

    if conversation_history:
        prompt += "\n\nالمحادثة السابقة:\n"
        for item in conversation_history[-10:]:
            role = item.get("role")
            content = item.get("content")
            if content:
                prompt += f"\n{role}: {content}"

    prompt += f"\n\nالسؤال الحالي:\n{user_message}\n\nأجب باللغة العربية."

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        return response.text or "عذراً، لم أتمكن من إنشاء إجابة حالياً."
    except Exception as e:
        error = str(e)
        print("GEMINI ERROR:", error)
        if "429" in error or "quota" in error.lower():
            return "⚠️ تم الوصول إلى حد استخدام Gemini حالياً. حاول مرة أخرى لاحقاً."
        if "API_KEY_INVALID" in error or "invalid api key" in error.lower():
            return "⚠️ مفتاح Gemini غير صحيح."
        return "⚠️ حدث خطأ أثناء الاتصال بالمستشار الذكي."

# =========================================================
# NEWSLETTER HELPERS
# =========================================================

def week_label():
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def build_weekly_issue():
    projects = KNOWLEDGE_BASE["المشاريع"]
    open_projects = [
        (name, data) for name, data in projects.items()
        if data["raised"] < data["target"]
    ]

    # This content is based only on platform data. External sector news can be added
    # later from an admin dashboard/API without inventing news in the newsletter.
    items = [
        {
            "title": "🔎 أبرز الفرص على المنصة",
            "text": "، ".join([f"{name} ({data['location']})" for name, data in open_projects]) or "لا توجد فرص مفتوحة حالياً."
        },
        {
            "title": "💰 حركة التمويل",
            "text": " | ".join([
                f"{name}: {data['raised']:,} من {data['target']:,} ريال"
                for name, data in projects.items()
            ])
        },
        {
            "title": "📊 ما يهم المستثمر هذا الأسبوع",
            "text": "تظهر المنصة لكل فرصة ثلاثة مؤشرات واضحة: مستوى المخاطر، جاذبية الاستثمار، وحالة الفحص المالي؛ بدلاً من استخدام نسبة ثقة قد تكون قابلة لتفسيرات مختلفة."
        },
        {
            "title": "📰 أخبار وتحديثات القطاع",
            "text": "تُضاف هنا أخبار القطاع السياحي المؤثرة على الاستثمار من مصادر موثوقة عند اعتمادها من فريق المنصة. لا يتم نشر خبر غير موثّق."
        },
        {
            "title": "🚀 تحديث المنصة",
            "text": "يمكن للمستثمر الانتقال من النشرة إلى المنصة مباشرة لاكتشاف الفرص وقراءة تفاصيلها ومراجعة بيانات الاستثمار."
        }
    ]

    return {
        "title": "Tourism Investment Newsletter | النشرة الأسبوعية للاستثمار السياحي",
        "week_label": f"الأسبوع — {week_label()}",
        "items": items
    }


def save_issue(issue):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO newsletter_issues (title, week_label, items_json, created_at) VALUES (?, ?, ?, ?)",
        (issue["title"], issue["week_label"], json.dumps(issue["items"], ensure_ascii=False), datetime.now(timezone.utc).isoformat())
    )
    issue_id = cur.lastrowid
    conn.commit()
    conn.close()
    return issue_id


def latest_issue():
    conn = db_connect()
    row = conn.execute("SELECT * FROM newsletter_issues ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        issue = build_weekly_issue()
        issue["id"] = save_issue(issue)
        return issue
    return {
        "id": row["id"],
        "title": row["title"],
        "week_label": row["week_label"],
        "items": json.loads(row["items_json"])
    }


def newsletter_html(issue):
    items_html = "".join(
        f"""
        <div style='padding:18px 0;border-bottom:1px solid #e6e1d7;'>
          <div style='font-size:18px;font-weight:700;color:#2F5D50;margin-bottom:7px;'>{escape(item['title'])}</div>
          <div style='font-size:14px;line-height:1.9;color:#43554D;'>{escape(item['text'])}</div>
        </div>
        """
        for item in issue["items"]
    )

    return f"""
    <!doctype html>
    <html lang='ar' dir='rtl'>
    <body style='margin:0;background:#f1e9da;font-family:Arial,Tahoma,sans-serif;color:#16241F;'>
      <div style='max-width:680px;margin:30px auto;background:#fff;border-radius:18px;overflow:hidden;border:1px solid #ded8cc;'>
        <div style='background:#2F5D50;color:#fff;padding:28px 30px;'>
          <div style='font-size:13px;opacity:.85;'>TOURISM INVESTMENT MARKET</div>
          <h1 style='margin:8px 0;font-size:25px;'>النشرة الأسبوعية للاستثمار السياحي</h1>
          <div style='font-size:13px;opacity:.9;'>{escape(issue['week_label'])}</div>
        </div>
        <div style='padding:24px 30px;'>
          <p style='font-size:15px;line-height:1.9;'>ملخص سريع يساعدك تتابع السوق الاستثماري السياحي وتعرف الفرص والتحديثات المهمة، حتى لو لم تكن تخطط للاستثمار حالياً.</p>
          {items_html}
          <div style='margin-top:24px;text-align:center;'>
            <a href='https://abdullatifmoh.github.io/hakthon/' style='display:inline-block;background:#C1652F;color:#fff;text-decoration:none;padding:13px 26px;border-radius:10px;font-weight:700;'>اكتشف الفرص داخل المنصة</a>
          </div>
          <p style='margin-top:24px;font-size:11px;color:#7a827e;line-height:1.8;'>هذه النشرة لأغراض المعلومات العامة وليست توصية استثمارية. يجب مراجعة تفاصيل كل فرصة وشروطها ومخاطرها قبل اتخاذ أي قرار.</p>
        </div>
      </div>
    </body>
    </html>
    """


def send_email(to_email, subject, html_body):
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER / SMTP_PASSWORD غير مضبوطين")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to_email
    msg.set_content("افتح الرسالة في بريد يدعم HTML لعرض النشرة الأسبوعية.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def send_issue_to_subscribers(issue_id, issue):
    conn = db_connect()
    users = conn.execute(
        "SELECT id, email FROM users WHERE newsletter_enabled = 1 AND email IS NOT NULL AND email != ''"
    ).fetchall()
    conn.close()

    html = newsletter_html(issue)
    sent = 0
    failed = 0

    for user in users:
        status = "sent"
        error_text = None
        try:
            send_email(user["email"], issue["title"], html)
            sent += 1
        except Exception as e:
            status = "failed"
            error_text = str(e)
            failed += 1

        conn = db_connect()
        conn.execute(
            "INSERT INTO newsletter_deliveries (issue_id, user_id, email, status, error, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (issue_id, user["id"], user["email"], status, error_text, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    return {"total": len(users), "sent": sent, "failed": failed}


def check_admin():
    supplied = request.headers.get("X-Newsletter-Admin-Token", "")
    return bool(supplied) and supplied == ADMIN_TOKEN

# =========================================================
# CHAT API
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"status": "error", "response": "اكتب سؤالك أولاً."}), 400

    answer = generate_ai_response(message.strip(), data.get("history", []))
    return jsonify({"status": "success", "response": answer, "ai": "gemini", "model": MODEL})

# =========================================================
# USER / NEWSLETTER SUBSCRIPTION
# =========================================================

@app.route("/api/users/register", methods=["POST"])
def register_user():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    role = str(data.get("role", "investor")).strip() or "investor"
    newsletter = bool(data.get("newsletter", True))

    if not EMAIL_RE.match(email):
        return jsonify({"status": "error", "response": "البريد الإلكتروني غير صحيح."}), 400

    now = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.execute("""
        INSERT INTO users (name, email, role, newsletter_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          name=excluded.name,
          role=excluded.role,
          newsletter_enabled=excluded.newsletter_enabled,
          updated_at=excluded.updated_at
    """, (name, email, role, 1 if newsletter else 0, now, now))
    conn.commit()
    row = conn.execute("SELECT id, newsletter_enabled FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    return jsonify({
        "status": "success",
        "user_id": row["id"],
        "newsletter_subscribed": bool(row["newsletter_enabled"]),
        "message": "تم حفظ الحساب وتفضيل النشرة الأسبوعية."
    })


@app.route("/api/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    role = str(data.get("role", "investor")).strip() or "investor"
    enabled = bool(data.get("enabled", True))

    if not EMAIL_RE.match(email):
        return jsonify({"status": "error", "response": "البريد الإلكتروني غير صحيح."}), 400

    now = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    conn.execute("""
        INSERT INTO users (name, email, role, newsletter_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          name=excluded.name,
          role=excluded.role,
          newsletter_enabled=excluded.newsletter_enabled,
          updated_at=excluded.updated_at
    """, (name, email, role, 1 if enabled else 0, now, now))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "newsletter_enabled": enabled})


@app.route("/api/newsletter/status", methods=["GET"])
def newsletter_status():
    email = str(request.args.get("email", "")).strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"status": "error", "response": "البريد الإلكتروني غير صحيح."}), 400

    conn = db_connect()
    row = conn.execute("SELECT email, newsletter_enabled FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    return jsonify({
        "status": "success",
        "found": bool(row),
        "newsletter_enabled": bool(row["newsletter_enabled"]) if row else False
    })

# =========================================================
# NEWSLETTER API
# =========================================================

@app.route("/api/newsletter/latest", methods=["GET"])
def newsletter_latest():
    return jsonify({"status": "success", "issue": latest_issue()})


@app.route("/api/newsletter/create", methods=["POST"])
def newsletter_create():
    if not check_admin():
        return jsonify({"status": "error", "response": "غير مصرح."}), 401

    data = request.get_json(silent=True) or {}
    issue = {
        "title": str(data.get("title") or "Tourism Investment Newsletter | النشرة الأسبوعية للاستثمار السياحي"),
        "week_label": str(data.get("week_label") or f"الأسبوع — {week_label()}"),
        "items": data.get("items") or build_weekly_issue()["items"]
    }

    if not isinstance(issue["items"], list):
        return jsonify({"status": "error", "response": "items يجب أن تكون قائمة."}), 400

    issue["id"] = save_issue(issue)
    return jsonify({"status": "success", "issue": issue})


@app.route("/api/newsletter/send-weekly", methods=["POST"])
def newsletter_send_weekly():
    if not check_admin():
        return jsonify({"status": "error", "response": "غير مصرح."}), 401

    issue = build_weekly_issue()
    issue["id"] = save_issue(issue)

    result = send_issue_to_subscribers(issue["id"], issue)
    return jsonify({"status": "success", "issue": issue, "delivery": result})


@app.route("/api/newsletter/send/<int:issue_id>", methods=["POST"])
def newsletter_send_existing(issue_id):
    if not check_admin():
        return jsonify({"status": "error", "response": "غير مصرح."}), 401

    conn = db_connect()
    row = conn.execute("SELECT * FROM newsletter_issues WHERE id = ?", (issue_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"status": "error", "response": "النشرة غير موجودة."}), 404

    issue = {
        "id": row["id"],
        "title": row["title"],
        "week_label": row["week_label"],
        "items": json.loads(row["items_json"])
    }
    result = send_issue_to_subscribers(issue_id, issue)
    return jsonify({"status": "success", "delivery": result})

# =========================================================
# PROJECTS / HEALTH
# =========================================================

@app.route("/api/projects", methods=["GET"])
def projects():
    return jsonify({"status": "success", "projects": KNOWLEDGE_BASE["المشاريع"]})


@app.route("/api/health", methods=["GET"])
def health():
    conn = db_connect()
    subscribers = conn.execute("SELECT COUNT(*) AS c FROM users WHERE newsletter_enabled = 1").fetchone()["c"]
    conn.close()
    return jsonify({
        "status": "online",
        "ai": "gemini",
        "configured": bool(GEMINI_API_KEY),
        "model": MODEL,
        "newsletter": {
            "configured": bool(SMTP_USER and SMTP_PASSWORD),
            "active_subscribers": subscribers
        }
    })


@app.route("/api/test-ai", methods=["GET"])
def test_ai():
    return jsonify({"status": "success", "response": generate_ai_response("اكتب جملة قصيرة تؤكد أن المستشار الذكي يعمل.")})


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "name": "Saudi Tourism Investment AI",
        "status": "online",
        "ai": "Gemini",
        "newsletter": "enabled"
    })


if __name__ == "__main__":
    print("=" * 70)
    print("Saudi Tourism Investment AI + Weekly Newsletter")
    print("AI:", MODEL)
    print("Gemini:", "OK" if GEMINI_API_KEY else "NOT SET")
    print("SMTP:", "OK" if SMTP_USER and SMTP_PASSWORD else "NOT SET")
    print("Database:", DATABASE_PATH)
    print("=" * 70)
    app.run(debug=True, host="0.0.0.0", port=5000)
