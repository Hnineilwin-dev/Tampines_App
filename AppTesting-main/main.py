import os
import uuid
import threading
from flask import Flask, request, jsonify, send_from_directory, render_template

from config import (
    PRIORITY_ORDER, AGENCY_ROUTING,
    SENDGRID_API_KEY, TWILIO_SID, TWILIO_TOKEN,
    GOOGLE_SHEET_ID, GOOGLE_CREDS_JSON,
    DEMO_MODE, TEST_MODE, TEST_EMAIL,
    FROM_EMAIL,
)
from agents import (
    generate_case_id, compute_priority,
    transcribe_audio, extract_issues_from_image,
    analyze_all_issues, resolve_routing, dispatch_agent,
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
os.makedirs('uploads', exist_ok=True)


# ─────────────────────────────────────────
# STATIC PAGE ROUTES  (separated frontend)
# ─────────────────────────────────────────
@app.route('/')
def index():
    """Root → serve login page."""
    return render_template('login.html')

@app.route('/login.html')
def login():
    return render_template('login.html')

@app.route('/home.html')
def home():
    return render_template('home.html')

@app.route('/profile.html')
def profile():
    return render_template('profile.html')

@app.route('/confirm.html')
def confirm():
    return render_template('confirm.html')

@app.route('/history.html')
def history():
    return render_template('history.html')

@app.route('/index.html')
def index_html():
    return render_template('home.html')

@app.route('/static/sw.js')
def serve_sw():
    response = send_from_directory('static', 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


# ─────────────────────────────────────────
# ANALYZE ENDPOINT
# ─────────────────────────────────────────
@app.route('/analyze', methods=['POST'])
def analyze():
    result = {
        "transcript":            None,
        "image_result":          None,
        "analysis":              None,
        "routes":                None,
        "location":              None,
        "case_id":               None,
        "dispatch":              None,
        "needs_clarification":   False,
        "clarification_question": "",
        "error":                 None
    }

    saved_image_paths = []

    try:
        audio_file    = request.files.get('audio')
        extra_context = request.form.get('extra_context', '')   # clarification follow-up

        location       = request.form.get('location', '')
        lat            = request.form.get('lat', '')
        lng            = request.form.get('lng', '')
        resident_phone = request.form.get('phone', '')
        resident_name  = request.form.get('name', '')

        if location:
            result["location"] = location
        elif lat and lng:
            result["location"] = f"{lat}, {lng}"

        # ── Step 1: Transcribe voice ──
        if audio_file:
            audio_path = os.path.join(
                app.config['UPLOAD_FOLDER'],
                'temp_audio.' + audio_file.filename.rsplit('.', 1)[-1]
            )
            audio_file.save(audio_path)
            result["transcript"] = transcribe_audio(audio_path)
            os.remove(audio_path)

        # ── Step 2: Multi-image extraction ──
        image_result = {"detected_labels": [], "description": "", "confidence": 50}

        raw_image_files = [request.files.get('image')]
        idx = 2
        while True:
            extra = request.files.get(f'image_{idx}')
            if extra is None:
                break
            raw_image_files.append(extra)
            idx += 1
        image_files = [f for f in raw_image_files if f is not None]

        if image_files:
            for img_file in image_files:
                ext  = img_file.filename.rsplit('.', 1)[-1] if '.' in img_file.filename else 'jpg'
                path = os.path.join(
                    app.config['UPLOAD_FOLDER'], f'case_{uuid.uuid4().hex[:8]}.{ext}'
                )
                img_file.save(path)
                saved_image_paths.append(path)
            image_result          = extract_issues_from_image(saved_image_paths)
            result["image_result"] = image_result

        # ── Step 3: Full multi-issue analysis + routing ──
        if result["transcript"] or image_result.get("detected_labels"):
            transcript = result["transcript"] or "No voice report provided"
            analysis   = analyze_all_issues(
                transcript, image_result, result["location"] or "", extra_context
            )
            result["analysis"] = analysis

            # Priority override from keyword engine
            computed_priority = compute_priority(
                analysis.get("final_labels", []),
                analysis.get("case_summary", "") + analysis.get("resident_message", "")
            )
            if PRIORITY_ORDER.index(computed_priority) < PRIORITY_ORDER.index(analysis.get("priority", "LOW")):
                analysis["priority"] = computed_priority

            # Check clarification needed
            if analysis.get("needs_clarification") and not extra_context:
                result["needs_clarification"]   = True
                result["clarification_question"] = analysis.get("clarification_question", "")
                result["case_id"]               = generate_case_id()
                return jsonify(result)

            # Resolve agency routes
            routes = resolve_routing(analysis.get("final_labels", []))
            if not routes:
                routes = [{
                    "agency":         "Town Council",
                    "email":          FROM_EMAIL,
                    "sla":            "3 working days",
                    "category":       "general",
                    "labels_covered": analysis.get("final_labels", [])
                }]
            result["routes"] = routes

        # ── Step 4: Generate case ID ──
        case_id        = generate_case_id()
        result["case_id"] = case_id

        # ── Step 5: Dispatch (wait up to 25 s) ──
        if result["analysis"] and result["routes"]:
            dispatch_sink  = {}
            dispatch_thread = threading.Thread(
                target=dispatch_agent,
                args=(
                    case_id,
                    result["analysis"],
                    result["routes"],
                    result["transcript"] or "",
                    result["location"]   or "",
                    resident_phone or None,
                    saved_image_paths if saved_image_paths else None,
                    resident_name  or None,
                ),
                kwargs={"result_sink": dispatch_sink},
                daemon=True
            )
            dispatch_thread.start()
            dispatch_thread.join(timeout=25)

            result["dispatch"] = {
                "status":       "dispatched",
                "agencies":     [r["agency"] for r in result["routes"]],
                "whatsapp_sent": dispatch_sink.get("sms", False),
                "email_sent":   dispatch_sink.get("emails_ok", False),
            }

    except Exception as e:
        result["error"] = str(e)
        for p in saved_image_paths:
            if os.path.exists(p):
                os.remove(p)

    return jsonify(result)


# ─────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({
        "status":              "ok",
        "demo_mode":           DEMO_MODE,
        "test_mode":           TEST_MODE,
        "test_email":          TEST_EMAIL if TEST_MODE else None,
        "issue_types_loaded":  len(AGENCY_ROUTING),
        "services": {
            "groq":      bool(os.getenv("GROQ_API_KEY")),
            "sendgrid":  bool(SENDGRID_API_KEY),
            "twilio":    bool(TWILIO_SID and TWILIO_TOKEN),
            "sheets":    bool(GOOGLE_SHEET_ID and GOOGLE_CREDS_JSON)
        }
    })


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, port=port, host='0.0.0.0')