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
