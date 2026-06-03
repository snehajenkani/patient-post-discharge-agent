from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os, re
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# PDF support
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("⚠ pdfplumber not installed. Run: pip install pdfplumber")

load_dotenv()
print("Loaded API Key:", os.getenv("GEMINI_API_KEY"))

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

app = Flask(__name__)
app.secret_key = "patient_agent_secret_key"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Global State ──
patient_info  = ""
patient_name  = ""
diagnosis     = ""
procedure     = ""
medications   = ""
diet          = ""
follow_up     = ""
upload_time   = ""
chat_history  = []
med_reminders = {}   # { "med_name": True/False }


# ── Helpers ──

def extract_field(text, *labels):
    for label in labels:
        match = re.search(rf"{label}\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_pdf_text(filepath):
    if not PDF_SUPPORT:
        return ""
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                pt = page.extract_text()
                if pt:
                    text += pt + "\n"
    except Exception as e:
        text = f"Error reading PDF: {e}"
    return text.strip()


def parse_medications(med_text):
    lines = [l.strip() for l in med_text.strip().split("\n") if l.strip()]
    result = []
    for line in lines:
        clean = re.sub(r"^[\d\.\-\*]+\s*", "", line).strip()
        if clean:
            parts = re.split(r"\s+[-]\s+", clean, maxsplit=1)
            result.append({
                "name":     parts[0].strip(),
                "schedule": parts[1].strip() if len(parts) > 1 else ""
            })
    return result


def parse_emergency_signs(text):
    if "Emergency Signs:" not in text:
        return []
    signs_text = text.split("Emergency Signs:")[1].strip()
    lines = [l.strip() for l in signs_text.split("\n") if l.strip()]
    return [re.sub(r"^[\-\*\d\.]+\s*", "", l).strip() for l in lines if l]


def calc_recovery_progress():
    score = 0
    if patient_name: score += 20
    if medications:  score += 20
    if diet:         score += 20
    if follow_up:    score += 20
    if chat_history: score += 20
    return score


def get_context(**extra):
    emergency_chats = [c for c in chat_history if "EMERGENCY" in c["bot"]]
    med_list = parse_medications(medications) if medications else []
    reminders = {med["name"]: med_reminders.get(med["name"], False) for med in med_list}
    return {
        "now":               datetime.now(),
        "patient_name":      patient_name,
        "diagnosis":         diagnosis,
        "procedure":         procedure,
        "medications":       medications,
        "diet":              diet,
        "follow_up":         follow_up,
        "patient_info":      patient_info,
        "upload_time":       upload_time,
        "chat_history":      chat_history,
        "med_count":         len(med_list),
        "med_list":          med_list,
        "med_reminders":     reminders,
        "emergency_count":   len(emergency_chats),
        "emergency_chats":   emergency_chats,
        "emergency_signs":   parse_emergency_signs(patient_info),
        "recovery_progress": calc_recovery_progress(),
        "pdf_support":       PDF_SUPPORT,
        **extra
    }


# ── Routes ──

@app.route("/", methods=["GET", "POST"])
def home():
    global chat_history
    response_text = ""

    if "upload_message" in session:
        response_text = session.pop("upload_message")

    elif request.method == "POST":
        user_message = request.form.get("message", "")
        message = user_message.lower()

        emergency_keywords = [
            "chest pain", "difficulty breathing", "can't breathe",
            "severe bleeding", "unconscious", "high fever"
        ]

        if any(k in message for k in emergency_keywords):
            response_text = "🚨 EMERGENCY ALERT\n\nPlease contact your doctor immediately\nor visit the nearest hospital."
        else:
            prompt = f"""
You are a Patient Post-Discharge Assistant.

Patient Information:
{patient_info}

Patient Details:
Name: {patient_name}
Diagnosis: {diagnosis}
Medications: {medications}
Diet: {diet}
Follow-Up: {follow_up}

Instructions:
- Answer ONLY using the discharge summary.
- Detect the language of the question and reply in the SAME language.
- Use simple language, bullet points, and keep answers short.
- Be friendly and use emojis where appropriate.
- If information is missing say so clearly.

Patient Question:
{user_message}
"""
            try:
                response = model.generate_content(prompt)
                response_text = response.text
            except Exception:
                response_text = "❌ Gemini API unavailable.\n\nYour quota may be exhausted. Please try again later."

        chat_history.insert(0, {"user": user_message, "bot": response_text})
        response_text = ""   # prevent double display

    return render_template("home.html", active_page="home", response=response_text, **get_context())


@app.route("/chats")
def chats():
    return render_template("chats.html", active_page="chats", **get_context())


@app.route("/clear_chats")
def clear_chats():
    global chat_history
    chat_history.clear()
    return redirect(url_for("chats"))


@app.route("/alerts")
def alerts():
    return render_template("alerts.html", active_page="alerts", **get_context())


@app.route("/summaries")
def summaries():
    return render_template("summaries.html", active_page="summaries", **get_context())


@app.route("/medications")
def medications_page():
    return render_template("medications.html", active_page="medications", **get_context())


@app.route("/followups")
def followups():
    return render_template("followups.html", active_page="followups", **get_context())

@app.route("/toggle_reminder/<int:med_index>")
def toggle_reminder(med_index):
    global med_reminders
    med_list = parse_medications(medications) if medications else []
    if 0 <= med_index < len(med_list):
        med_name = med_list[med_index]["name"]
        med_reminders[med_name] = not med_reminders.get(med_name, False)
    return redirect(url_for("medications_page"))

@app.route("/reset_reminders")
def reset_reminders():
    global med_reminders
    med_reminders = {}
    return redirect(url_for("medications_page"))


@app.route("/voice_query", methods=["POST"])
def voice_query():
    global chat_history
    data = request.get_json()
    user_message = data.get("message", "").strip()
    lang = data.get("lang", "en-US")

    if not user_message:
        return jsonify({"response": "I didn't catch that. Please try again."}), 400

    message = user_message.lower()
    emergency_keywords = [
        "chest pain", "difficulty breathing", "can't breathe",
        "severe bleeding", "unconscious", "high fever",
        "నొప్పి", "రక్తస్రావం", "జ్వరం",
        "सीने में दर्द", "सांस", "बुखार",
        "மார்பு வலி", "காய்ச்சல்"
    ]

    if any(k in message for k in emergency_keywords):
        response_text = "Emergency alert! Please contact your doctor immediately."
    else:
        # Tell Gemini exactly which language to reply in
        lang_map = {
            "te-IN": "Telugu",
            "hi-IN": "Hindi",
            "ta-IN": "Tamil",
            "kn-IN": "Kannada",
            "ml-IN": "Malayalam",
            "mr-IN": "Marathi",
            "bn-IN": "Bengali",
            "en-US": "English",
            "en-IN": "English"
        }
        reply_language = lang_map.get(lang, "English")

        prompt = f"""
You are a Patient Post-Discharge Assistant.
You MUST reply ONLY in {reply_language} language.
Answer in 1-2 short sentences only, suitable for voice reading.
Do NOT use any other language.

Patient: {patient_name}
Diagnosis: {diagnosis}
Medications: {medications}
Follow-Up: {follow_up}

Question: {user_message}

Reply in {reply_language} only:
"""
        try:
            response = model.generate_content(prompt)
            response_text = response.text
        except Exception:
            response_text = "Sorry, I could not connect to the AI. Please try again later."

    chat_history.insert(0, {"user": f"🎤 {user_message}", "bot": response_text})
    return jsonify({"response": response_text, "lang": lang})
@app.route("/upload", methods=["POST"])
def upload_file():
    global patient_info, patient_name, diagnosis, procedure
    global medications, diet, follow_up, chat_history, upload_time, med_reminders

    file = request.files.get("file")

    if file and file.filename != "":
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        ext = file.filename.rsplit(".", 1)[-1].lower()

        if ext == "pdf":
            if not PDF_SUPPORT:
                session["upload_message"] = "❌ PDF support not installed. Run: pip install pdfplumber"
                return redirect(url_for("home"))
            patient_info = extract_pdf_text(filepath)
            if not patient_info or patient_info.startswith("Error"):
                session["upload_message"] = "❌ Could not read PDF. Make sure it has selectable text (not scanned)."
                return redirect(url_for("home"))
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                patient_info = f.read()

        # Reset everything
        chat_history.clear()
        med_reminders = {}
        upload_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
        patient_name = diagnosis = procedure = medications = diet = follow_up = ""

        # Parse fields
        patient_name = extract_field(patient_info, "Patient Name", "Name")
        diagnosis    = extract_field(patient_info, "Diagnosis")
        procedure    = extract_field(patient_info, "Procedure")

        if "Medications:" in patient_info:
            after = patient_info.split("Medications:")[1]
            medications = after.split("Diet Instructions:")[0].strip() if "Diet Instructions:" in after else after.strip()

        if "Diet Instructions:" in patient_info:
            after = patient_info.split("Diet Instructions:")[1]
            diet = after.split("Follow-Up:")[0].strip() if "Follow-Up:" in after else after.strip()

        if "Follow-Up:" in patient_info:
            after = patient_info.split("Follow-Up:")[1]
            follow_up = after.split("Emergency Signs:")[0].strip() if "Emergency Signs:" in after else after.strip()

        print(f"\n===== PARSED =====")
        print(f"NAME      : {patient_name}")
        print(f"DIAGNOSIS : {diagnosis}")
        print(f"PROCEDURE : {procedure}")
        print(f"FOLLOW-UP : {follow_up}")
        print(f"MEDS      : {medications[:80]}")
        print(f"==================\n")

        session["upload_message"] = f"✅ {'PDF' if ext == 'pdf' else 'File'} uploaded successfully!"
        return redirect(url_for("home"))

    session["upload_message"] = "❌ Please choose a file first."
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True, host='localhost')

