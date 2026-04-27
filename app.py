from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
import requests
import pymysql

app = Flask(__name__)
CORS(app, origins="*")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DB_HOST     = os.environ.get("DB_HOST", "")
DB_NAME     = os.environ.get("DB_NAME", "school2")
DB_USER     = os.environ.get("DB_USER", "")
DB_PASS     = os.environ.get("DB_PASS", "")
DB_PORT     = int(os.environ.get("DB_PORT", "3306"))

# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────
def get_db():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10
    )

def save_history(user_id, message, reply):
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (user_id, message, reply) VALUES (%s, %s, %s)",
                (user_id, message, reply)
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

# ─────────────────────────────────────────────
# Groq helper
# ─────────────────────────────────────────────
def call_groq(messages, json_mode=False):
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.1,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
            },
            json=payload,
            timeout=45,
        )
        data = r.json()
        if r.status_code == 200:
            return {"ok": True, "text": data["choices"][0]["message"]["content"]}
        return {"ok": False, "error": data.get("error", {}).get("message", "api_error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─────────────────────────────────────────────
# Wael special response
# ─────────────────────────────────────────────
WAEL_REPLY = (
    "هو الأقوى، سيدُ السيفِ والكلماتِ،<br>\n"
    "إمبراطورُ المجدِ الذي لا يَفنى أثرُهُ في الراياتِ.<br>\n"
    "يا سائلاً عن وائلٍ، فلتعلمْ: هو عزمُ الريحِ إن هَدَرَتْ،<br>\n"
    "وهو النورُ إن أقبل، وهو الفخرُ إن ازدهرَتْ الحكاياتِ.<br><br>\n"
    "إنهُ أعظمُ الأباطرة: <b>Wael the Mighty</b> — أقوى الرجالِ."
)

# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────
CLASSIFY_SYSTEM = """You are a classifier for a school league chatbot called 'دوري التخصصات'.
Decide if the user message needs DB data or can be answered directly.
Reply with JSON ONLY:
{"type": "db"}   — needs specific school data (names, scores, rankings, quiz results, schedules)
{"type": "chat"} — general conversation, greetings, how-to questions about the site, simple general knowledge

Examples:
- 'مين أعلى طالب نقاط' → {"type": "db"}
- 'كم عدد الطلاب' → {"type": "db"}
- 'كيف اشترك بالمسابقة' → {"type": "chat"}
- 'مرحبا' → {"type": "chat"}
- 'شو هو الذكاء الاصطناعي' → {"type": "chat"}"""

CHAT_SYSTEM = """أنت مساعد ودود ومختصر لموقع 'دوري التخصصات' المدرسي.
الموقع يحتوي على: مسابقات، ألعاب تعليمية، اختبارات، تخصصات (هندسة، إدارة أعمال، تكنولوجيا معلومات)، نقاط وترتيب.
- أجب بالعربية إذا السؤال بالعربية.
- كن مختصراً — جملة أو جملتين كافيتين.
- يمكنك الإجابة على أسئلة عامة بسيطة بشكل مختصر.
- لا تكتب تقارير أو قوائم طويلة.
- لا تتكلم في السياسة أو المواضيع الحساسة."""

SQL_SYSTEM = """You are a strict School Database Assistant for MariaDB database 'school2'.
Return JSON ONLY: {"sql": "SELECT ...", "refusal": null} OR {"sql": null, "refusal": "رسالة رفض بالعربية"}

Rules:
- Only SELECT queries. No INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/GRANT/REVOKE.
- Add LIMIT 100 for large results.
- Use EXACT column names below. Do NOT invent columns.
- For points/ranking questions: join quiz_participations or game_results with students.

Schema:
students(student_id VARCHAR, full_name VARCHAR, email VARCHAR, grade VARCHAR, specialty VARCHAR, class_id VARCHAR, username VARCHAR, created_at TIMESTAMP)
teachers(teacher_id VARCHAR, full_name VARCHAR, grades VARCHAR, subjects VARCHAR, specialty VARCHAR, username VARCHAR, created_at TIMESTAMP)
specialties(code VARCHAR, name VARCHAR)
specialty_points(id INT, grade VARCHAR, specialty VARCHAR, total_points INT, students_count INT, last_updated TIMESTAMP)
quizzes(id INT, title VARCHAR, grade VARCHAR, specialty VARCHAR, subject VARCHAR, num_questions INT, total_points INT, duration_minutes INT, created_by VARCHAR, created_at TIMESTAMP)
quiz_sessions(id INT, quiz_id INT, session_code VARCHAR, status ENUM('pending','active','completed','cancelled'), started_at DATETIME, ends_at DATETIME, created_at TIMESTAMP)
quiz_participations(id INT, session_id INT, student_id VARCHAR, student_name VARCHAR, specialty VARCHAR, grade VARCHAR, score INT, correct_count INT, max_score INT, started_at TIMESTAMP, completed_at DATETIME)
game_results(id INT, game_id INT, student_id VARCHAR, score INT, flips INT, matches INT, completed_at TIMESTAMP)
games(id INT, name VARCHAR, type VARCHAR, specialty VARCHAR)
competitions(id INT, title VARCHAR, type VARCHAR, specialty VARCHAR, grade VARCHAR, subject VARCHAR, total_points INT, questions_count INT, published TINYINT, created_at TIMESTAMP)
competition_sessions(id INT, competition_id INT, session_code VARCHAR, status ENUM('pending','active','completed','cancelled'), started_at DATETIME, ends_at DATETIME, created_at TIMESTAMP)
game_jam_submissions(id INT, competition_id INT, student_id VARCHAR, points_awarded INT, rank INT, submitted_at DATETIME)
grades(id INT, student_id VARCHAR, grade VARCHAR, specialty VARCHAR, subject VARCHAR, month_1 FLOAT, month_2 FLOAT, month_3 FLOAT, final_exam FLOAT, created_at TIMESTAMP)
admins(student_id VARCHAR, role VARCHAR)
chat_history(id INT, user_id VARCHAR, message TEXT, reply TEXT, created_at TIMESTAMP)

Examples:
SELECT s.full_name, SUM(qp.score) AS total_score FROM quiz_participations qp JOIN students s ON s.student_id = qp.student_id GROUP BY qp.student_id, s.full_name ORDER BY total_score DESC LIMIT 1;
SELECT s.full_name, SUM(gr.score) AS total_score FROM game_results gr JOIN students s ON s.student_id = gr.student_id GROUP BY gr.student_id, s.full_name ORDER BY total_score DESC LIMIT 1;"""

SUMMARY_SYSTEM = "أنت مساعد يلخص بيانات نظام المدرسة باختصار وبالعربية."

FORBIDDEN_KW = ["insert","update","delete","drop","alter","truncate","create","grant","revoke"]

# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "school chatbot"})

@app.route("/chatbot_api.php", methods=["POST", "GET", "OPTIONS"])
def chatbot():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = request.args.get("user_id")
    if not user_id:
        body = request.get_json(silent=True) or {}
        user_id = body.get("user_id")
    action  = request.args.get("action")

    # ── get_history ──
    if action == "get_history":
        if not user_id:
            return jsonify({"success": False, "message": "auth_required"})
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT message AS user_message, reply AS bot_reply, created_at "
                    "FROM chat_history WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",
                    (user_id,)
                )
                rows = cur.fetchall()
            conn.close()
            return jsonify({"success": True, "history": rows})
        except Exception as e:
            return jsonify({"success": False, "message": "db_error", "error": str(e)})

    # ── clear_history ──
    if action == "clear_history":
        if not user_id:
            return jsonify({"success": False, "message": "auth_required"})
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_history WHERE user_id=%s", (user_id,))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "message": "db_error", "error": str(e)})

    # ── main chat ──
    if not user_id:
        return jsonify({
            "success": False,
            "message": "auth_required",
            "reply": "عذراً، يجب عليك تسجيل الدخول أولاً لاستخدام المساعد الذكي."
        })

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")

    # Wael easter egg
    low = last_user.lower()
    if any(w in low for w in ["wael", "وائل", "وايل"]):
        save_history(user_id, last_user, WAEL_REPLY)
        return jsonify({"success": True, "reply": WAEL_REPLY})

    if not last_user:
        return jsonify({"success": False, "reply": "لم أفهم سؤالك، حاول مرة أخرى."})

    # ── Classify ──
    classify_resp = call_groq([
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user",   "content": last_user},
    ], json_mode=True)

    q_type = "db"
    if classify_resp["ok"]:
        try:
            q_type = json.loads(classify_resp["text"]).get("type", "db")
        except Exception:
            pass

    # ── General chat ──
    if q_type == "chat":
        resp = call_groq([
            {"role": "system", "content": CHAT_SYSTEM},
            {"role": "user",   "content": last_user},
        ])
        if not resp["ok"]:
            return jsonify({"success": False, "reply": "يوجد مشكلة في الاتصال، يرجى المحاولة لاحقاً."})
        reply = resp["text"].strip()
        save_history(user_id, last_user, reply)
        return jsonify({"success": True, "reply": reply})

    # ── SQL pipeline ──
    sql_resp = call_groq([
        {"role": "system", "content": SQL_SYSTEM},
        {"role": "user",   "content": last_user},
    ], json_mode=True)

    if not sql_resp["ok"]:
        return jsonify({"success": False, "reply": "يوجد مشكلة في الاتصال، يرجى المحاولة لاحقاً."})

    try:
        sql_data = json.loads(sql_resp["text"])
    except Exception:
        return jsonify({"success": False, "message": "invalid_sql_json"})

    refusal = (sql_data.get("refusal") or "").strip()
    if refusal:
        save_history(user_id, last_user, refusal)
        return jsonify({"success": True, "reply": refusal})

    sql = (sql_data.get("sql") or "").strip()
    if not sql:
        msg = "أنا مساعد تعليمي مخصص للإجابة على أسئلة نظام المدرسة فقط."
        save_history(user_id, last_user, msg)
        return jsonify({"success": True, "reply": msg})

    # Safety check
    low_sql = sql.lower()
    for kw in FORBIDDEN_KW:
        if kw in low_sql:
            return jsonify({"success": False, "message": "forbidden_sql_keyword"})
    if not re.match(r'^\s*(select|with)\s', sql, re.IGNORECASE):
        return jsonify({"success": False, "message": "only_select_allowed"})
    if not re.search(r'\blimit\s+\d+', sql, re.IGNORECASE):
        sql += " LIMIT 100"

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({"success": False, "message": "db_error", "error": str(e), "sql": sql})

    # Summarize
    summary_resp = call_groq([
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user",   "content": f"السؤال: {last_user}\nالبيانات: {json.dumps(rows, ensure_ascii=False)}"},
    ])
    if not summary_resp["ok"]:
        return jsonify({"success": True, "reply": "تم تنفيذ الاستعلام لكن حدثت مشكلة في التلخيص.", "data": rows})

    reply = summary_resp["text"].strip()
    save_history(user_id, last_user, reply)
    return jsonify({"success": True, "reply": reply, "data": rows, "sql": sql})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
