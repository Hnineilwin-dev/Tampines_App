import os
import base64
import json
import uuid
import threading
from datetime import datetime
from PIL import Image
import io

from config import (
    client, AGENCY_ROUTING, PRIORITY_KEYWORDS, PRIORITY_ORDER,
    SENDGRID_API_KEY, TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM_PHONE,
    GOOGLE_SHEET_ID, GOOGLE_CREDS_JSON,
    FROM_EMAIL, FROM_NAME,
    DEMO_MODE, TEST_MODE, TEST_EMAIL, TEST_PHONE,
)

ISSUE_LABEL_LIST = ", ".join(AGENCY_ROUTING.keys())


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def generate_case_id():
    suffix = uuid.uuid4().hex[:4].upper()
    year = datetime.now().year
    return f"TMP-{year}-{suffix}"


def compress_image(image_path, max_size_kb=1000):
    img = Image.open(image_path)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    max_dim = 1024
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    buffer = io.BytesIO()
    quality = 85
    while quality > 20:
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality)
        if buffer.tell() <= max_size_kb * 1024:
            break
        quality -= 10
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


def compute_priority(detected_labels: list, description: str) -> str:
    """Return the highest matching priority level."""
    text = (description + " " + " ".join(detected_labels)).lower()
    for level in PRIORITY_ORDER:
        for kw in PRIORITY_KEYWORDS[level]:
            if kw in text:
                return level
    return "LOW"


# ─────────────────────────────────────────
# COMPONENT 1: VOICE → TEXT (Whisper)
# ─────────────────────────────────────────
def transcribe_audio(audio_path):
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), audio_file.read()),
            model="whisper-large-v3",
            language=None,
            response_format="text"
        )
    return transcription


# ─────────────────────────────────────────
# COMPONENT 2: MULTI-ISSUE EXTRACTOR (Llama Vision)
# ─────────────────────────────────────────
def extract_issues_from_image(image_paths):
    """Return a JSON object with all detected issue labels from one or more images."""
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    prompt = f"""You are an AI assistant for Singapore HDB estate issue reporting.

Analyze ALL provided images and detect every estate issue present across all of them.

Return ONLY valid JSON — no markdown, no explanation — in this exact format:
{{
  "detected_labels": ["label1", "label2"],
  "description": "One sentence describing all issues seen across all images",
  "confidence": 85
}}

Valid labels (pick only from this list): {ISSUE_LABEL_LIST}

Rules:
- List every issue you can see across ALL images, not just one
- confidence is 0-100
- If nothing estate-related is visible in any image, return detected_labels as []"""

    content = []
    for path in image_paths:
        image_data = compress_image(path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}})
    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": content}],
        max_tokens=300
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"detected_labels": [], "description": raw, "confidence": 40}


# ─────────────────────────────────────────
# COMPONENT 3: MULTI-ISSUE ANALYSIS (Llama 70B)
# ─────────────────────────────────────────
def analyze_all_issues(transcript: str, image_result: dict, location: str, extra_context: str = ""):
    """
    Merge voice + image signals, confirm/extend labels, determine priority,
    check if clarification is needed, and compose the smart user response.
    """
    labels_from_image = image_result.get("detected_labels", [])
    img_description   = image_result.get("description", "")
    img_confidence    = image_result.get("confidence", 50)

    prompt_system = f"""You are an intelligent multi-issue estate routing AI for Tampines HDB, Singapore.

Your job:
1. Merge information from the resident's voice report and image analysis
2. Identify ALL distinct issues present — a single photo can have multiple problems
3. For each issue, pick the best matching label from the approved list
4. Determine overall priority: CRITICAL / HIGH / MEDIUM / LOW
5. If confidence < 60, set needs_clarification=true and write a follow-up question
6. Compose a smart, friendly resident_message that:
   - Names every agency being notified
   - Lists "What to do NOW" safety steps if HIGH or CRITICAL
   - Gives SLA expectations
   - Is warm and empathetic
7. Write a concise case_summary for officers

Valid labels: {ISSUE_LABEL_LIST}

Priority guide:
- CRITICAL: fire, explosion, gas leak, structural collapse, trapped persons → tell resident to call 995
- HIGH: exposed live wire, active flooding, bee swarm, blocked fire exit, lift entrapment
- MEDIUM: broken pipe, fallen tree, pest, overflowing bin, pothole, ceiling leak
- LOW: litter, noise, overgrown grass, graffiti, minor damage

Respond ONLY in valid JSON — no markdown:
{{
  "final_labels": ["label1", "label2"],
  "priority": "HIGH",
  "confidence": 82,
  "needs_clarification": false,
  "clarification_question": "",
  "agencies_notified": ["Agency A", "Agency B"],
  "resident_message": "Full friendly message with safety steps and SLA",
  "case_summary": "Officer-facing brief",
  "estimated_responses": {{"Agency A": "4 hours", "Agency B": "24 hours"}}
}}"""

    prompt_user = f"""Voice transcript: "{transcript or 'No voice report'}"

Image analysis: {img_description}
Image detected labels: {labels_from_image}
Image confidence: {img_confidence}%

Location: {location or 'Not provided'}
Additional context: {extra_context or 'None'}

Produce the routing JSON now."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt_system},
            {"role": "user",   "content": prompt_user}
        ],
        max_tokens=700,
        temperature=0.25
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {
            "final_labels": labels_from_image or ["illegal_dump"],
            "priority": "MEDIUM",
            "confidence": 50,
            "needs_clarification": False,
            "clarification_question": "",
            "agencies_notified": ["Town Council"],
            "resident_message": "Your report has been received. We will look into it shortly.",
            "case_summary": raw,
            "estimated_responses": {}
        }


# ─────────────────────────────────────────
# COMPONENT 4: RESOLVE ROUTING FOR LABELS
# ─────────────────────────────────────────
def resolve_routing(final_labels: list) -> list:
    """
    Return a deduplicated list of agency routing entries for all detected labels.
    Each entry: {agency, email, sla, category, labels_covered}
    """
    seen_agencies = {}
    for label in final_labels:
        route = AGENCY_ROUTING.get(label)
        if not route:
            continue
        agency = route["agency"]
        if agency not in seen_agencies:
            seen_agencies[agency] = {
                "agency": agency,
                "email": route["email"],
                "sla": route["sla"],
                "category": route["category"],
                "labels_covered": []
            }
        seen_agencies[agency]["labels_covered"].append(label)
    return list(seen_agencies.values())


# ─────────────────────────────────────────
# COMPONENT 5: EMAIL BUILDER & SENDER
# ─────────────────────────────────────────
def send_email_to_agency(case_id, analysis, route_entry, transcript, location,
                         image_paths=None, resident_phone=None, resident_name=None):
    if DEMO_MODE:
        print(f"[DEMO] Would email {route_entry['agency']} for case {case_id}")
        return True
    if not SENDGRID_API_KEY:
        print("[WARN] SENDGRID_API_KEY not set — skipping email")
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

        priority = analysis.get("priority", "MEDIUM")
        priority_emoji = {"CRITICAL": "🔴🔴", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority, "🟡")
        labels_str = ", ".join(route_entry.get("labels_covered", []))
        to_email = TEST_EMAIL if TEST_MODE and TEST_EMAIL else route_entry["email"]

        subject = (f"{priority_emoji} [{case_id}] Estate Report — {route_entry['agency']} "
                   f"| {labels_str} | {location or 'Location TBC'}")

        now_str = datetime.now().strftime('%d %b %Y, %I:%M %p SGT')

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;">
          <div style="background:#1a2f6e;padding:22px 24px;border-radius:10px 10px 0 0;">
            <h2 style="color:white;margin:0;font-size:20px;">🏢 Tampines Estate — Case Report</h2>
            <p style="color:rgba(255,255,255,0.6);margin:6px 0 0;font-size:13px;">
              Auto-dispatched by AI Estate Reporter
            </p>
          </div>
          <div style="background:#f8f9ff;padding:26px;border:1px solid #dde3f0;">
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
              <tr><td style="padding:8px 0;color:#6b7a99;width:160px;">Case ID</td>
                  <td style="padding:8px 0;font-weight:bold;font-size:18px;color:#1a2f6e;">{case_id}</td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Assigned Agency</td>
                  <td style="padding:8px 0;font-weight:bold;">{route_entry['agency']}</td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Detected Issues</td>
                  <td style="padding:8px 0;">{labels_str.replace('_',' ')}</td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Priority</td>
                  <td style="padding:8px 0;">{priority_emoji} <strong>{priority}</strong></td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Location</td>
                  <td style="padding:8px 0;">{location or 'Not provided'}</td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Reported at</td>
                  <td style="padding:8px 0;">{now_str}</td></tr>
              <tr><td style="padding:8px 0;color:#6b7a99;">Response target</td>
                  <td style="padding:8px 0;">{route_entry['sla']}</td></tr>
              {f'<tr><td style="padding:8px 0;color:#6b7a99;">Resident Name</td><td style="padding:8px 0;font-weight:bold;">{resident_name}</td></tr>' if resident_name else ''}
              {f'<tr><td style="padding:8px 0;color:#6b7a99;">Resident Contact</td><td style="padding:8px 0;"><a href="tel:{resident_phone}" style="color:#1a2f6e;font-weight:bold;">{resident_phone}</a> <span style="color:#6b7a99;font-size:12px;">(consented to agency contact)</span></td></tr>' if resident_phone else ''}
            </table>
            <div style="background:white;border-left:4px solid #1a2f6e;padding:16px;border-radius:4px;margin-bottom:16px;">
              <p style="color:#6b7a99;font-size:12px;margin:0 0 6px;text-transform:uppercase;letter-spacing:1px;">Case Summary</p>
              <p style="margin:0;">{analysis.get('case_summary','No summary provided.')}</p>
            </div>
            {'<div style="background:white;border-left:4px solid #f0a500;padding:16px;border-radius:4px;margin-bottom:16px;"><p style="color:#6b7a99;font-size:12px;margin:0 0 6px;text-transform:uppercase;letter-spacing:1px;">Resident Voice Transcript</p><p style="margin:0;font-style:italic;">' + str(transcript) + '</p></div>' if transcript and transcript != 'No voice report provided' else ''}
            <div style="background:#fff7ed;border-left:4px solid #f0a500;padding:14px 16px;border-radius:4px;">
              <p style="margin:0;font-size:13px;color:#92400e;">
                ℹ️ This email was also sent to other relevant agencies for this case.
                All agencies should coordinate with the case reference <strong>{case_id}</strong>.
              </p>
            </div>
          </div>
          <div style="background:#1a2f6e;padding:12px 20px;border-radius:0 0 10px 10px;text-align:center;">
            <p style="color:rgba(255,255,255,0.5);font-size:12px;margin:0;">
              Tampines AI Estate Reporter • Auto-dispatched • Do not reply to this email
            </p>
          </div>
        </div>
        """

        message = Mail(
            from_email=(FROM_EMAIL, FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=html_body
        )

        if image_paths:
            if isinstance(image_paths, str):
                image_paths = [image_paths]
            attachments = []
            for idx, img_path in enumerate(image_paths):
                if not os.path.exists(img_path):
                    continue
                with open(img_path, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode()
                suffix = f"_{idx+1}" if idx > 0 else ""
                attachment = Attachment(
                    FileContent(encoded),
                    FileName(f'incident_photo{suffix}.jpg'),
                    FileType('image/jpeg'),
                    Disposition('attachment')
                )
                attachments.append(attachment)
            if attachments:
                message.attachment = attachments

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        resp = sg.send(message)
        print(f"[EMAIL] Sent to {to_email} ({route_entry['agency']}) — status {resp.status_code}")
        return resp.status_code in (200, 201, 202)

    except Exception as e:
        print(f"[EMAIL ERROR] {route_entry['agency']}: {e}")
        return False


def _normalize_phone(phone: str) -> str:
    """Ensure phone has E.164 format with leading +. Adds +65 if 8-digit SG number."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        if phone.startswith("65") and len(phone) == 10:
            phone = "+" + phone
        elif len(phone) == 8:          # bare SG mobile
            phone = "+65" + phone
        else:
            phone = "+" + phone        # best-effort
    return phone


def send_sms_to_resident(case_id, analysis, routes, resident_phone):
    if DEMO_MODE:
        print(f"[DEMO] Would WhatsApp/SMS {resident_phone}")
        return True
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM_PHONE, resident_phone]):
        missing = [k for k, v in {
            "TWILIO_SID": TWILIO_SID, "TWILIO_TOKEN": TWILIO_TOKEN,
            "TWILIO_FROM_PHONE": TWILIO_FROM_PHONE, "resident_phone": resident_phone
        }.items() if not v]
        print(f"[WARN] Twilio config incomplete — missing: {missing} — skipping WhatsApp/SMS")
        return False

    try:
        from twilio.rest import Client as TwilioClient

        priority = analysis.get("priority", "MEDIUM")
        priority_emoji = {"CRITICAL": "🔴🔴", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority, "🟡")
        agencies_str = ", ".join([r["agency"] for r in routes])
        msg = (
            f"✅ *Tampines Estate Reporter*\n\n"
            f"Case ID: *{case_id}*\n"
            f"{priority_emoji} Priority: {priority}\n"
            f"🏢 Notified: {agencies_str}\n\n"
            f"Thank you for keeping Tampines safe! 🌿"
        )

        to_phone   = _normalize_phone(TEST_PHONE if TEST_MODE and TEST_PHONE else resident_phone)
        from_phone = _normalize_phone(TWILIO_FROM_PHONE)

        print(f"[WA] Attempting WhatsApp: from=whatsapp:{from_phone} to=whatsapp:{to_phone}")
        twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

        # ── Try WhatsApp first ──
        wa_error = None
        try:
            msg_obj = twilio_client.messages.create(
                body=msg,
                from_=f"whatsapp:{from_phone}",
                to=f"whatsapp:{to_phone}"
            )
            print(f"[WA] ✅ WhatsApp sent to {to_phone} — SID {msg_obj.sid} — Status {msg_obj.status}")
            return True
        except Exception as e:
            wa_error = e
            print(f"[WA] ⚠️  WhatsApp failed: {e} — falling back to plain SMS")

        # ── Fallback: plain SMS ──
        try:
            msg_obj = twilio_client.messages.create(
                body=msg,
                from_=from_phone,
                to=to_phone
            )
            print(f"[SMS] ✅ Fallback SMS sent to {to_phone} — SID {msg_obj.sid} — Status {msg_obj.status}")
            return True
        except Exception as sms_e:
            print(f"[SMS] ❌ Fallback SMS also failed: {sms_e}")
            print(f"[SMS] Original WhatsApp error was: {wa_error}")
            return False

    except Exception as e:
        print(f"[WA/SMS FATAL ERROR] {e}")
        return False


def log_to_google_sheets(case_id, analysis, routes, transcript, location,
                         dispatch_results, resident_phone=None, resident_name=None):
    if DEMO_MODE:
        print(f"[DEMO] Would log {case_id} to Sheets")
        return True
    if not GOOGLE_SHEET_ID or not GOOGLE_CREDS_JSON:
        print("[WARN] Google Sheets config missing — skipping log")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)

        EXPECTED_HEADERS = [
            "Case ID", "Timestamp", "Labels", "Priority",
            "Agencies", "SLAs", "Location", "Transcript",
            "Case Summary", "Email Sent", "SMS Sent",
            "Confidence", "Needs Clarification", "Resident Name", "Resident Phone", "Status"
        ]

        try:
            worksheet = sh.worksheet("Cases")
        except Exception:
            worksheet = sh.add_worksheet(title="Cases", rows=1000, cols=len(EXPECTED_HEADERS))
            worksheet.append_row(EXPECTED_HEADERS)
            print("[SHEETS] Created new 'Cases' worksheet with headers")

        # ── Header sync: update row 1 if it's missing or outdated ──
        existing_headers = worksheet.row_values(1)
        if existing_headers != EXPECTED_HEADERS:
            if len(EXPECTED_HEADERS) > worksheet.col_count:
                worksheet.add_cols(len(EXPECTED_HEADERS) - worksheet.col_count)
            header_range = f"A1:{chr(ord('A') + len(EXPECTED_HEADERS) - 1)}1"
            worksheet.update(header_range, [EXPECTED_HEADERS])
            print(f"[SHEETS] Header synced: {existing_headers} → {EXPECTED_HEADERS}")

        agencies_str = " | ".join([r["agency"] for r in routes])
        slas_str     = " | ".join([r["sla"]    for r in routes])
        labels_str   = ", ".join(analysis.get("final_labels", []))

        row = [
            case_id,
            datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            labels_str,
            analysis.get("priority", ""),
            agencies_str,
            slas_str,
            location or '',
            transcript or '',
            analysis.get("case_summary", ""),
            '✅' if dispatch_results.get("emails_ok") else '❌',
            '✅' if dispatch_results.get("sms")       else '❌',
            str(analysis.get("confidence", "")),
            str(analysis.get("needs_clarification", False)),
            resident_name  or '',
            resident_phone or '',
            'Open'
        ]
        worksheet.append_row(row)
        print(f"[SHEETS] Logged case {case_id}")
        return True

    except Exception as e:
        print(f"[SHEETS ERROR] {e}")
        return False


# ─────────────────────────────────────────
# COMPONENT 6: PARALLEL DISPATCH AGENT
# ─────────────────────────────────────────
def dispatch_agent(case_id, analysis, routes, transcript, location,
                   resident_phone=None, image_paths=None, resident_name=None,
                   result_sink=None):
    """
    Dispatches emails, WhatsApp/SMS, and logs to Sheets in parallel.
    Writes final results into result_sink dict so the HTTP thread can read them.
    """
    print(f"\n{'='*55}")
    print(f"[AGENT] Dispatching {case_id}")
    print(f"[AGENT] Labels: {analysis.get('final_labels')} | Priority: {analysis.get('priority')}")
    print(f"[AGENT] Agencies: {[r['agency'] for r in routes]}")
    if TEST_MODE:
        print(f"[AGENT] TEST MODE — emails→{TEST_EMAIL}  phone→{TEST_PHONE or resident_phone}")
    print(f"{'='*55}\n")

    results = {"emails_ok": False, "sms": False, "sheets": False}
    email_threads  = []
    email_statuses = []

    def send_one(route_entry):
        ok = send_email_to_agency(
            case_id, analysis, route_entry, transcript, location,
            image_paths, resident_phone, resident_name
        )
        email_statuses.append(ok)

    # Parallel email dispatch
    for route in routes:
        t = threading.Thread(target=send_one, args=(route,), daemon=True)
        email_threads.append(t)
        t.start()
    for t in email_threads:
        t.join(timeout=20)

    results["emails_ok"] = all(email_statuses) if email_statuses else False

    # WhatsApp / SMS to resident
    if resident_phone:
        results["sms"] = send_sms_to_resident(case_id, analysis, routes, resident_phone)
    else:
        print("[AGENT] No resident_phone provided — skipping WhatsApp/SMS")

    # Log to Google Sheets
    results["sheets"] = log_to_google_sheets(
        case_id, analysis, routes, transcript, location,
        results, resident_phone, resident_name
    )

    print(f"\n[AGENT] Dispatch complete for {case_id}: {results}\n")

    if result_sink is not None:
        result_sink.update(results)

    return results