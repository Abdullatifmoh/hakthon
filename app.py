from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
import os
import json

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)
CORS(app)


# =========================================================
# GEMINI
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL = "gemini-3.6-flash"

client = None

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# DATABASE
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
            "risk": "متوسط",
            "potential": "عالية",
            "guide": "المرشد خالد المالكي",
            "analysis": "مشروع ترفيهي موسمي في أبها يستهدف العائلات خلال موسم الصيف. الموقع استراتيجي والطلب مرتفع."
        },

        "مخيم نجوم العلا": {
            "location": "العلا، المدينة المنورة",
            "sector": "ضيافة وإقامة",
            "target": 120000,
            "raised": 64200,
            "shares": 120,
            "price": 1000,
            "risk": "منخفض",
            "potential": "عالية",
            "guide": "المرشدة سارة الحربي",
            "analysis": "مخيم فاخر في العلا، وجهة سياحية عالمية. العوائد المتوقعة مرتفعة والمخاطر منخفضة."
        },

        "جولات كورنيش جدة": {
            "location": "جدة، مكة المكرمة",
            "sector": "جولات وفعاليات",
            "target": 80000,
            "raised": 80000,
            "shares": 80,
            "price": 1000,
            "risk": "منخفض",
            "potential": "متوسطة",
            "guide": "المرشد عمر الزهراني",
            "analysis": "تم تمويل المشروع بالكامل. نموذج تشغيلي مستدام مع إمكانية التوسع."
        },

        "واحة الأحساء التراثية": {
            "location": "الأحساء، المنطقة الشرقية",
            "sector": "ترفيه موسمي",
            "target": 90000,
            "raised": 42000,
            "shares": 90,
            "price": 1000,
            "risk": "متوسط",
            "potential": "متوسطة",
            "guide": "المرشد عبدالرحمن الحربي",
            "analysis": "مشروع يجمع بين التراث والترفيه في الأحساء. يحتاج إلى تسويق قوي."
        }
    },

    "المخاطر": {
        "types": [
            "الموسمية",
            "التنافسية",
            "التغيرات التنظيمية",
            "العوامل الخارجية"
        ],
        "advice": "نوّع استثماراتك، اختر مناطق مستقرة، ادرس الجدوى المالية، واستشر خبيراً."
    },

    "العوائد": {
        "average": "8-15% سنوياً",
        "factors": [
            "موقع المشروع",
            "جودة الخدمات",
            "استراتيجية التسويق",
            "إدارة التكاليف"
        ]
    },

    "الملكية": {
        "formula": "نسبة الملكية = (عدد الأسهم / إجمالي الأسهم) × 100",
        "rights": [
            "أرباح سنوية",
            "تقارير مالية",
            "التصويت",
            "الاجتماعات"
        ]
    }
}


# =========================================================
# DATABASE TEXT
# =========================================================

def get_knowledge_context():

    return json.dumps(
        KNOWLEDGE_BASE,
        ensure_ascii=False,
        indent=2
    )


# =========================================================
# AI SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
أنت "المستشار الذكي" داخل منصة سعودية للاستثمار في المشاريع السياحية.

تحدث مع المستخدم باللغة العربية، ويفضل باللهجة السعودية البسيطة عندما يكون السؤال عامياً.

وظيفتك:

1. مساعدة المستخدم على فهم الاستثمار.
2. شرح المشاريع الموجودة في المنصة.
3. مقارنة المشاريع.
4. حساب المبالغ والأسهم ونسب الملكية.
5. شرح المخاطر والعوائد.
6. مساعدة المستثمر المبتدئ.
7. الإجابة بشكل طبيعي واحترافي.

قواعد مهمة:

- لا تخترع بيانات عن المشاريع.
- استخدم قاعدة البيانات الموجودة أسفل هذه التعليمات.
- إذا لم توجد المعلومة في قاعدة البيانات، قل إنها غير متوفرة.
- لا تخترع نسب عوائد جديدة.
- لا تدّعي أنك مستشار مالي مرخص.
- القرار الاستثماري النهائي للمستخدم.
- الاستثمار يحمل مخاطر.
- استخدم الريال السعودي.
- إذا كان السؤال بسيطاً، اجعل الإجابة قصيرة.
- إذا كان السؤال يحتاج حساباً، قم بالحساب.
- استخدم نقاطاً وعناوين عندما تكون مفيدة.
- لا تكرر نفس الجملة.
- افهم اللهجة السعودية.

أمثلة:

المستخدم:
وش أفضل مشروع؟

المستخدم:
لو معي 5000 ريال وش أقدر أشتري؟

المستخدم:
وش أفضل العلا ولا أبها؟

المستخدم:
كم باقي على تمويل المشروع؟

المستخدم:
احسب لي 3 أسهم.

المستخدم:
كم نسبة ملكيتي؟

المستخدم:
وش مخاطر الاستثمار؟

المستخدم:
أنا مبتدئ بالاستثمار، وش تنصحني أفهم أول؟

المستخدم:
ليش مشروع العلا مخاطره منخفضة؟

أجب بشكل واضح وسهل.
"""


# =========================================================
# GENERATE AI RESPONSE
# =========================================================

def generate_ai_response(user_message, conversation_history=None):

    # -----------------------------------------------------
    # Check API key
    # -----------------------------------------------------

    if not GEMINI_API_KEY:

        return (
            "⚠️ مفتاح Gemini API غير موجود.\n\n"
            "تأكد من إضافة GEMINI_API_KEY في PowerShell."
        )


    if client is None:

        return "⚠️ تعذر تشغيل Gemini."


    # -----------------------------------------------------
    # Database
    # -----------------------------------------------------

    knowledge = get_knowledge_context()


    # -----------------------------------------------------
    # Build prompt
    # -----------------------------------------------------

    prompt = SYSTEM_PROMPT

    prompt += "\n\n"
    prompt += "=============================\n"
    prompt += "بيانات منصة الاستثمار\n"
    prompt += "=============================\n"

    prompt += knowledge


    # -----------------------------------------------------
    # Conversation history
    # -----------------------------------------------------

    if conversation_history:

        prompt += "\n\n"
        prompt += "=============================\n"
        prompt += "المحادثة السابقة\n"
        prompt += "=============================\n"

        for item in conversation_history[-10:]:

            role = item.get("role")
            content = item.get("content")

            if not content:
                continue

            if role == "user":

                prompt += "\nالمستخدم: "
                prompt += str(content)

            elif role == "assistant":

                prompt += "\nالمستشار: "
                prompt += str(content)


    # -----------------------------------------------------
    # Current question
    # -----------------------------------------------------

    prompt += "\n\n"
    prompt += "=============================\n"
    prompt += "السؤال الحالي\n"
    prompt += "=============================\n"

    prompt += user_message

    prompt += "\n\nأجب باللغة العربية."


    # -----------------------------------------------------
    # Gemini request
    # -----------------------------------------------------

    try:

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        answer = response.text


        if not answer:

            return "عذراً، لم أتمكن من إنشاء إجابة حالياً."


        return answer


    except Exception as e:

        error = str(e)

        print("\n")
        print("=" * 70)
        print("GEMINI ERROR")
        print("=" * 70)
        print(error)
        print("=" * 70)
        print("\n")


        # -------------------------------------------------
        # API KEY ERROR
        # -------------------------------------------------

        if (
            "API_KEY_INVALID" in error
            or "invalid api key" in error.lower()
            or "invalid_argument" in error.lower()
        ):

            return (
                "⚠️ مفتاح Gemini غير صحيح.\n\n"
                "تأكد من نسخ API Key الصحيح من Google AI Studio."
            )


        # -------------------------------------------------
        # QUOTA
        # -------------------------------------------------

        if "429" in error:

            return (
                "⚠️ تم الوصول إلى حد استخدام Gemini حالياً.\n\n"
                "حاول مرة أخرى بعد قليل."
            )


        if "quota" in error.lower():

            return (
                "⚠️ تم الوصول إلى حد الاستخدام المتاح لـ Gemini."
            )


        # -------------------------------------------------
        # GENERAL ERROR
        # -------------------------------------------------

        return (
            "⚠️ حدث خطأ أثناء الاتصال بالمستشار الذكي.\n\n"
            "تفاصيل الخطأ:\n"
            + error
        )


# =========================================================
# CHAT API
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json(silent=True)


        if not data:

            return jsonify({
                "status": "error",
                "response": "لم يتم إرسال البيانات."
            }), 400


        user_message = data.get("message", "")


        if not isinstance(user_message, str):

            return jsonify({
                "status": "error",
                "response": "الرسالة غير صحيحة."
            }), 400


        user_message = user_message.strip()


        if not user_message:

            return jsonify({
                "status": "error",
                "response": "اكتب سؤالك أولاً."
            }), 400


        conversation_history = data.get(
            "history",
            []
        )


        answer = generate_ai_response(
            user_message,
            conversation_history
        )


        return jsonify({

            "status": "success",

            "response": answer,

            "ai": "gemini",

            "model": MODEL

        })


    except Exception as e:

        print("SERVER ERROR:", str(e))

        return jsonify({

            "status": "error",

            "response": "حدث خطأ في الخادم."

        }), 500


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({

        "status": "online",

        "ai": "gemini",

        "configured": bool(GEMINI_API_KEY),

        "model": MODEL,

        "message": "Gemini AI Server is running"

    })


# =========================================================
# PROJECTS API
# =========================================================

@app.route("/api/projects", methods=["GET"])
def projects():

    return jsonify({

        "status": "success",

        "projects": KNOWLEDGE_BASE["المشاريع"]

    })


# =========================================================
# TEST GEMINI
# =========================================================

@app.route("/api/test-ai", methods=["GET"])
def test_ai():

    try:

        if not GEMINI_API_KEY:

            return jsonify({

                "status": "error",

                "message": "GEMINI_API_KEY is not configured"

            }), 500


        answer = generate_ai_response(
            "اكتب جملة قصيرة جداً تؤكد أن المستشار الذكي يعمل."
        )


        return jsonify({

            "status": "success",

            "ai": "gemini",

            "model": MODEL,

            "response": answer

        })


    except Exception as e:

        print("TEST ERROR:", str(e))

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({

        "name": "Saudi Tourism Investment AI",

        "status": "online",

        "ai": "Gemini",

        "model": MODEL

    })


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("Saudi Tourism Investment AI")
    print("=" * 70)
    print("AI PROVIDER: Google Gemini")
    print("MODEL:", MODEL)


    if GEMINI_API_KEY:

        print("GEMINI_API_KEY: OK")

    else:

        print("GEMINI_API_KEY: NOT SET")
        print()
        print(
            'PowerShell command: '
            '$env:GEMINI_API_KEY="YOUR_KEY"'
        )


    print("=" * 70)
    print()


    app.run(

        debug=True,

        host="0.0.0.0",

        port=5000

    )