from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
import json
import os
import re
import smtplib
import sqlite3

# ============================================================
# APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://abdullatifmoh.github.io",
                "http://localhost:5000",
                "http://127.0.0.1:5000",
            ]
        }
    },
)

# ============================================================
# ENVIRONMENT
# ============================================================

DATABASE_PATH = os.getenv("DATABASE_PATH", "tourism_investment.db")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

NEWSLETTER_ADMIN_TOKEN = os.getenv("NEWSLETTER_ADMIN_TOKEN", "")

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://abdullatifmoh.github.io/hakthon/",
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)

# ============================================================
# DATABASE
# ============================================================

def db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def init_database():
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'investor',
            newsletter_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            week_label TEXT NOT NULL,
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
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

    connection.commit()
    connection.close()


init_database()

# ============================================================
# PLATFORM DATA
# ============================================================

PROJECTS = {
    "واحة أبها الترفيهية": {
        "location": "أبها، عسير",
        "sector": "ترفيه موسمي",
        "target": 50000,
        "raised": 38000,
        "shares": 50,
        "price": 1000,
        "risk": "منخفض",
        "attractiveness": "متوسطة",
        "financial_check": "مكتمل",
        "guide": "خالد المالكي",
        "analysis": "الموقع استراتيجي والطلب السياحي مناسب، مع بقاء جزء من الميزانية غير مصروف.",
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
        "financial_check": "مكتمل",
        "guide": "سارة الحربي",
        "analysis": "وجهة سياحية قوية، والتمويل الحالي أقل من الميزانية المستهدفة.",
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
        "financial_check": "مكتمل",
        "guide": "عمر الزهراني",
        "analysis": "تم تمويل المشروع بالكامل وفق البيانات الحالية، مع إمكانية التوسع.",
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
        "financial_check": "مكتمل",
        "guide": "عبدالرحمن الحربي",
        "analysis": "المشروع يجمع بين التراث والترفيه ويحتاج إلى تسويق قوي.",
    },
}

SECTOR_UPDATES = [
    {
        "title": "📈 حركة السوق السياحي الاستثماري",
        "text": "يتابع المستثمر الفرص الجديدة وحركة التمويل وتحديثات المشاريع من داخل المنصة.",
    },
    {
        "title": "📰 أخبار القطاع",
        "text": "تُضاف الأخبار المؤثرة على الاستثمار بعد اعتمادها من فريق المنصة؛ لا يتم إنشاء أخبار غير موثقة.",
    },
    {
        "title": "💡 ما يهم المستثمر",
        "text": "تظهر لكل فرصة ثلاثة مؤشرات واضحة: مستوى المخاطر، جاذبية الاستثمار، وحالة الفحص المالي.",
    },
]


def platform_context():
    return json.dumps(
        {
            "projects": PROJECTS,
            "sector_updates": SECTOR_UPDATES,
        },
        ensure_ascii=False,
        indent=2,
    )

# ============================================================
# GEMINI
# ============================================================

SYSTEM_PROMPT = """
أنت المستشار الذكي داخل منصة سعودية للاستثمار في المشاريع السياحية.

تحدث بالعربية وبأسلوب واضح واحترافي.

قواعد مهمة:
1) استخدم بيانات المنصة المرفقة فقط عند الحديث عن أرقام المشاريع.
2) لا تخترع مشروعاً أو رقماً أو عائداً.
3) إذا لم تتوفر معلومة، قل إنها غير متوفرة.
4) لا تستخدم مؤشر "الثقة" أو نسبة نجاح عشوائية.
5) عند تقييم الفرصة استخدم:
   - مستوى المخاطر
   - جاذبية الاستثمار
   - الفحص المالي
6) القرار الاستثماري النهائي للمستخدم.
7) لا تقدم نفسك كمستشار مالي مرخص.
8) ذكّر بالمخاطر عند الحاجة.
"""


def ask_gemini(message, history=None):
    if not gemini_client:
        return "⚠️ المستشار الذكي غير مفعّل حالياً. أضف GEMINI_API_KEY في إعدادات السيرفر."

    prompt = SYSTEM_PROMPT
    prompt += "\n\nبيانات المنصة:\n" + platform_context()

    if history:
        prompt += "\n\nآخر المحادثة:\n"
        for item in history[-10:]:
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            if content:
                prompt += f"\n{role}: {content}"

    prompt += f"\n\nسؤال المستخدم:\n{message}\n\nأجب بالعربية."

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text or "لم أتمكن من إنشاء إجابة حالياً."
    except Exception as exc:
        error = str(exc)
        print("Gemini error:", error)

        if "429" in error or "quota" in error.lower():
            return "⚠️ تم الوصول إلى حد استخدام Gemini حالياً. حاول لاحقاً."
        if "invalid" in error.lower() and "key" in error.lower():
            return "⚠️ مفتاح Gemini غير صحيح."

        return "⚠️ حدث خطأ أثناء الاتصال بالمستشار الذكي."

# ============================================================
# NEWSLETTER
# ============================================================

def build_newsletter_issue():
    open_projects = [
        (name, data)
        for name, data in PROJECTS.items()
        if data["raised"] < data["target"]
    ]

    opportunities = []
    for name, data in open_projects:
        remaining = data["target"] - data["raised"]
        opportunities.append(
            f"{name} — {data['location']} — المتبقي للتمويل: {remaining:,} ريال"
        )

    funding = []
    for name, data in PROJECTS.items():
        percentage = round((data["raised"] / data["target"]) * 100)
        funding.append(
            f"{name}: {data['raised']:,} / {data['target']:,} ريال ({percentage}%)"
        )

    items = [
        {
            "title": "🔎 فرص جديدة ومفتوحة",
            "text": "لاكتشاف الفرص المتاحة هذا الأسبوع:\n"
                    + ("\n".join(opportunities) if opportunities else "لا توجد فرص مفتوحة حالياً."),
        },
        {
            "title": "💰 حركة التمويل",
            "text": "\n".join(funding),
        },
        {
            "title": "📊 مؤشرات الاستثمار",
            "text": (
                "بدلاً من مؤشر الثقة غير الواضح، تعرض المنصة لكل فرصة: "
                "مستوى المخاطر، جاذبية الاستثمار، والفحص المالي."
            ),
        },
    ]

    items.extend(SECTOR_UPDATES)

    items.append(
        {
            "title": "🚀 من النشرة إلى المنصة",
            "text": (
                "النشرة ليست مجرد أخبار؛ هدفها أن تبقي المستثمر مرتبطاً بالسوق، "
                "ثم تنقله مباشرة إلى المنصة لاكتشاف الفرصة وقراءة تفاصيلها."
            ),
        }
    )

    return {
        "title": "Tourism Investment Newsletter | النشرة الأسبوعية للاستثمار السياحي",
        "week_label": datetime.now().strftime("أسبوع %Y-%m-%d"),
        "items": items,
    }


def save_newsletter(issue):
    connection = db()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO newsletter_issues
        (title, week_label, items_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            issue["title"],
            issue["week_label"],
            json.dumps(issue["items"], ensure_ascii=False),
            utc_now(),
        ),
    )

    issue_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return issue_id


def get_latest_newsletter():
    connection = db()
    row = connection.execute(
        """
        SELECT id, title, week_label, items_json, created_at
        FROM newsletter_issues
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    connection.close()

    if not row:
        issue = build_newsletter_issue()
        issue["id"] = save_newsletter(issue)
        return issue

    return {
        "id": row["id"],
        "title": row["title"],
        "week_label": row["week_label"],
        "items": json.loads(row["items_json"]),
        "created_at": row["created_at"],
    }


def newsletter_html(issue):
    item_blocks = []

    for item in issue["items"]:
        title = escape(str(item.get("title", "")))
        text = escape(str(item.get("text", ""))).replace("\n", "<br>")

        item_blocks.append(
            f"""
            <div style="
                margin:0 0 16px;
                padding:16px;
                border:1px solid #DDE6E1;
                border-radius:14px;
                background:#F8FAF8;
            ">
                <div style="
                    font-weight:700;
                    color:#2F5D50;
                    margin-bottom:7px;
                    font-size:16px;
                ">{title}</div>
                <div style="
                    color:#33413B;
                    line-height:1.9;
                    font-size:14px;
                ">{text}</div>
            </div>
            """
        )

    return f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{escape(issue["title"])}</title>
    </head>
    <body style="
      margin:0;
      padding:20px;
      background:#EFE8DA;
      font-family:Arial,Tahoma,sans-serif;
      color:#16241F;
    ">
      <div style="
        max-width:680px;
        margin:auto;
        background:#FFFFFF;
        border-radius:20px;
        overflow:hidden;
      ">
        <div style="
          padding:28px 24px;
          background:#2F5D50;
          color:#FFFFFF;
        ">
          <div style="font-size:13px;opacity:.8;">Tourism Investment Market</div>
          <h1 style="margin:8px 0 5px;font-size:25px;">
            النشرة الأسبوعية للاستثمار السياحي
          </h1>
          <div style="font-size:13px;opacity:.85;">
            {escape(issue["week_label"])}
          </div>
        </div>

        <div style="padding:24px;">
          <p style="line-height:1.9;font-size:15px;">
            ملخص أسبوعي للسوق السياحي الاستثماري:
            الفرص، التمويل، أخبار القطاع وأهم التحديثات.
          </p>

          {''.join(item_blocks)}

          <div style="text-align:center;margin-top:24px;">
            <a href="{escape(FRONTEND_URL)}"
               style="
                 display:inline-block;
                 background:#C1652F;
                 color:#FFFFFF;
                 text-decoration:none;
                 padding:13px 25px;
                 border-radius:10px;
                 font-weight:700;
               ">
              اكتشف الفرص داخل المنصة
            </a>
          </div>

          <p style="
            margin-top:25px;
            color:#7B8580;
            font-size:11px;
            line-height:1.8;
          ">
            هذه النشرة لأغراض المعلومات العامة وليست توصية استثمارية.
            يجب مراجعة تفاصيل كل فرصة وشروطها ومخاطرها قبل اتخاذ أي قرار.
          </p>
        </div>
      </div>
    </body>
    </html>
    """


def send_email(to_email, subject, html_body):
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER و SMTP_PASSWORD غير مضبوطين.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM or SMTP_USER
    message["To"] = to_email

    message.set_content(
        "النشرة الأسبوعية للاستثمار السياحي. افتح الرسالة في بريد يدعم HTML."
    )
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


def send_issue(issue_id, issue):
    connection = db()
    subscribers = connection.execute(
        """
        SELECT id, email
        FROM users
        WHERE newsletter_enabled = 1
          AND email <> ''
        ORDER BY id
        """
    ).fetchall()
    connection.close()

    body = newsletter_html(issue)

    sent = 0
    failed = 0

    for subscriber in subscribers:
        status = "sent"
        error_message = None

        try:
            send_email(
                subscriber["email"],
                issue["title"],
                body,
            )
            sent += 1
        except Exception as exc:
            failed += 1
            status = "failed"
            error_message = str(exc)
            print("Newsletter email error:", subscriber["email"], error_message)

        connection = db()
        connection.execute(
            """
            INSERT INTO newsletter_deliveries
            (issue_id, user_id, email, status, error, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                subscriber["id"],
                subscriber["email"],
                status,
                error_message,
                utc_now(),
            ),
        )
        connection.commit()
        connection.close()

    return {
        "total": len(subscribers),
        "sent": sent,
        "failed": failed,
    }


def send_issue_to_email(issue_id, issue, email, user_id):
    """Send the latest newsletter immediately to one subscribed user."""
    body = newsletter_html(issue)
    status = "sent"
    error_message = None

    try:
        send_email(email, issue["title"], body)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        print("Immediate newsletter email error:", email, error_message)

    connection = db()
    connection.execute(
        """
        INSERT INTO newsletter_deliveries
        (issue_id, user_id, email, status, error, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (issue_id, user_id, email, status, error_message, utc_now()),
    )
    connection.commit()
    connection.close()

    if status == "failed":
        raise RuntimeError(error_message or "فشل إرسال النشرة.")

    return True


def admin_authorized():
    if not NEWSLETTER_ADMIN_TOKEN:
        return False
    return (
        request.headers.get("X-Newsletter-Admin-Token", "")
        == NEWSLETTER_ADMIN_TOKEN
    )

# ============================================================
# USER API
# ============================================================

def valid_email(email):
    return bool(EMAIL_RE.match(email))


@app.post("/api/users/register")
def register_user():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    role = str(data.get("role", "investor")).strip() or "investor"
    newsletter = bool(data.get("newsletter", True))

    if not valid_email(email):
        return jsonify(
            {"status": "error", "response": "البريد الإلكتروني غير صحيح."}
        ), 400

    now = utc_now()

    connection = db()
    connection.execute(
        """
        INSERT INTO users
        (name, email, role, newsletter_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          name = excluded.name,
          role = excluded.role,
          newsletter_enabled = excluded.newsletter_enabled,
          updated_at = excluded.updated_at
        """,
        (
            name,
            email,
            role,
            1 if newsletter else 0,
            now,
            now,
        ),
    )
    connection.commit()

    user = connection.execute(
        """
        SELECT id, name, email, role, newsletter_enabled
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()

    connection.close()

    return jsonify(
        {
            "status": "success",
            "user_id": user["id"],
            "newsletter_subscribed": bool(user["newsletter_enabled"]),
            "message": "تم حفظ الحساب وبيانات النشرة.",
        }
    )


@app.post("/api/newsletter/subscribe")
def subscribe_newsletter():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    role = str(data.get("role", "investor")).strip() or "investor"
    enabled = bool(data.get("enabled", True))

    if not valid_email(email):
        return jsonify(
            {"status": "error", "response": "البريد الإلكتروني غير صحيح."}
        ), 400

    now = utc_now()

    connection = db()
    connection.execute(
        """
        INSERT INTO users
        (name, email, role, newsletter_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          name = excluded.name,
          role = excluded.role,
          newsletter_enabled = excluded.newsletter_enabled,
          updated_at = excluded.updated_at
        """,
        (
            name,
            email,
            role,
            1 if enabled else 0,
            now,
            now,
        ),
    )
    connection.commit()
    connection.close()

    return jsonify(
        {
            "status": "success",
            "newsletter_enabled": enabled,
            "message": "تم تحديث تفضيل النشرة.",
        }
    )


@app.get("/api/newsletter/status")
def newsletter_status():
    email = str(request.args.get("email", "")).strip().lower()

    if not valid_email(email):
        return jsonify(
            {"status": "error", "response": "البريد الإلكتروني غير صحيح."}
        ), 400

    connection = db()
    user = connection.execute(
        """
        SELECT email, newsletter_enabled
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()
    connection.close()

    return jsonify(
        {
            "status": "success",
            "found": bool(user),
            "newsletter_enabled": bool(user["newsletter_enabled"]) if user else False,
        }
    )

# ============================================================
# NEWSLETTER API
# ============================================================

@app.get("/api/newsletter/latest")
def newsletter_latest():
    return jsonify(
        {
            "status": "success",
            "issue": get_latest_newsletter(),
        }
    )


@app.post("/api/newsletter/create")
def create_newsletter():
    if not admin_authorized():
        return jsonify(
            {"status": "error", "response": "غير مصرح."}
        ), 401

    data = request.get_json(silent=True) or {}

    default = build_newsletter_issue()

    issue = {
        "title": str(data.get("title") or default["title"]),
        "week_label": str(data.get("week_label") or default["week_label"]),
        "items": data.get("items") or default["items"],
    }

    if not isinstance(issue["items"], list):
        return jsonify(
            {"status": "error", "response": "items يجب أن تكون قائمة."}
        ), 400

    issue["id"] = save_newsletter(issue)

    return jsonify(
        {
            "status": "success",
            "issue": issue,
        }
    )


@app.post("/api/newsletter/send-weekly")
def send_weekly_newsletter():
    if not admin_authorized():
        return jsonify(
            {"status": "error", "response": "غير مصرح."}
        ), 401

    issue = build_newsletter_issue()
    issue["id"] = save_newsletter(issue)

    result = send_issue(issue["id"], issue)

    return jsonify(
        {
            "status": "success",
            "issue": issue,
            "delivery": result,
        }
    )


@app.post("/api/newsletter/send/<int:issue_id>")
def send_existing_newsletter(issue_id):
    if not admin_authorized():
        return jsonify(
            {"status": "error", "response": "غير مصرح."}
        ), 401

    connection = db()
    row = connection.execute(
        """
        SELECT id, title, week_label, items_json
        FROM newsletter_issues
        WHERE id = ?
        """,
        (issue_id,),
    ).fetchone()
    connection.close()

    if not row:
        return jsonify(
            {"status": "error", "response": "النشرة غير موجودة."}
        ), 404

    issue = {
        "id": row["id"],
        "title": row["title"],
        "week_label": row["week_label"],
        "items": json.loads(row["items_json"]),
    }

    result = send_issue(issue["id"], issue)

    return jsonify(
        {
            "status": "success",
            "delivery": result,
        }
    )

@app.post("/api/newsletter/send-now")
def send_newsletter_now():
    """Send the latest newsletter immediately to the logged-in user's email."""
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    if not valid_email(email):
        return jsonify({
            "status": "error",
            "response": "البريد الإلكتروني غير صحيح.",
        }), 400

    connection = db()
    user = connection.execute(
        """
        SELECT id, email, newsletter_enabled
        FROM users
        WHERE email = ?
        """,
        (email,),
    ).fetchone()
    connection.close()

    if not user:
        return jsonify({
            "status": "error",
            "response": "البريد غير مسجل في المنصة.",
        }), 404

    if not bool(user["newsletter_enabled"]):
        return jsonify({
            "status": "error",
            "response": "فعّل النشرة الأسبوعية أولاً.",
        }), 400

    try:
        issue = get_latest_newsletter()
        send_issue_to_email(issue["id"], issue, user["email"], user["id"])

        return jsonify({
            "status": "success",
            "message": "تم إرسال النشرة فورًا إلى بريدك الإلكتروني.",
            "email": user["email"],
            "issue": issue,
        })
    except Exception as exc:
        print("Immediate newsletter error:", str(exc))
        return jsonify({
            "status": "error",
            "response": "تعذر إرسال النشرة حالياً. تأكد من إعدادات البريد.",
        }), 500


# ============================================================
# AI / PROJECTS / HEALTH
# ============================================================

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not message:
        return jsonify(
            {"status": "error", "response": "اكتب سؤالك أولاً."}
        ), 400

    answer = ask_gemini(message, history)

    return jsonify(
        {
            "status": "success",
            "response": answer,
            "ai": "gemini",
            "model": GEMINI_MODEL,
        }
    )


@app.get("/api/projects")
def projects():
    return jsonify(
        {
            "status": "success",
            "projects": PROJECTS,
        }
    )


@app.get("/api/health")
def health():
    connection = db()

    subscribers = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM users
        WHERE newsletter_enabled = 1
        """
    ).fetchone()["count"]

    users = connection.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]

    connection.close()

    return jsonify(
        {
            "status": "online",
            "ai": {
                "configured": bool(GEMINI_API_KEY),
                "model": GEMINI_MODEL,
            },
            "newsletter": {
                "smtp_configured": bool(SMTP_USER and SMTP_PASSWORD),
                "admin_token_configured": bool(NEWSLETTER_ADMIN_TOKEN),
                "active_subscribers": subscribers,
                "total_users": users,
            },
            "database": DATABASE_PATH,
        }
    )


@app.get("/")
def home():
    return jsonify(
        {
            "name": "Saudi Tourism Investment Market",
            "status": "online",
            "features": [
                "AI assistant",
                "user storage",
                "weekly tourism investment newsletter",
                "email delivery",
            ],
        }
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("=" * 65)
    print("Saudi Tourism Investment Market")
    print("Gemini:", "ON" if GEMINI_API_KEY else "OFF")
    print("SMTP:", "ON" if SMTP_USER and SMTP_PASSWORD else "OFF")
    print("Database:", DATABASE_PATH)
    print("=" * 65)

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
