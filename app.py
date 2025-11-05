#!/usr/bin/env python3
import os
import time
import uuid
import re
import json
from io import BytesIO

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from werkzeug.utils import secure_filename

# Optional PDF support
try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# ------------------------
# Configuration
# ------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "gpt-3.5-turbo")

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"pdf", "txt"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", 20))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", 16000))

# ------------------------
# Flask init
# ------------------------
app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# In-memory session store (replace with DB for production)
sessions = {}

# ------------------------
# Utilities
# ------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    if PyPDF2 is None:
        raise RuntimeError("PyPDF2 is required for PDF parsing. Install with `pip install PyPDF2`.")
    try:
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        parts = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            parts.append(txt)
        return "\n".join(parts).strip()
    except Exception as e:
        print("❌ PDF extraction error:", e)
        return ""

def extract_text_from_txt_bytes(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8", errors="replace")
    except Exception:
        return file_bytes.decode("latin-1", errors="replace")

# System prompt tuned for friendly, improvised replies
SYSTEM_PROMPT = (
    "You are an experienced, friendly, and creative enterprise assistant. "
    "Respond in a warm, conversational, and slightly improvised tone — like a helpful colleague who can explain things clearly, "
    "add a tiny anecdote or relatable example when appropriate, and ask one short clarifying question if needed. "
    "Keep the response professional but human. Aim for 2-7 sentences unless user asks for brevity. "
    "When summarizing documents, provide a concise title (5 words max), 3–6 bullets with key points, and one short suggested action."
)

# ------------------------
# OpenRouter call
# ------------------------
def call_openrouter_chat(messages, temperature=0.8, max_tokens=512, model=OPENROUTER_MODEL):
    """
    Sends a chat completion request to OpenRouter in OpenAI-compatible format.
    messages: list of {"role": "system"/"user"/"assistant", "content": "..."}
    Returns (content_str_or_None, status_tag)
    """
    if not OPENROUTER_API_KEY:
        print("⚠️ OPENROUTER_API_KEY not provided; skipping live API call.")
        return None, "missing_api_key"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        print("🔗 OpenRouter status:", resp.status_code)
        if resp.status_code != 200:
            print("❗ OpenRouter response:", resp.text)
            return None, f"api_error_{resp.status_code}"
        data = resp.json()

        # Expect OpenAI style: choices[0].message.content
        content = None
        if isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and len(choices) > 0:
                c0 = choices[0]
                msg = c0.get("message")
                if isinstance(msg, dict) and "content" in msg:
                    content = msg["content"]
                elif "text" in c0:
                    content = c0.get("text")
            # Fallbacks
            if not content:
                content = data.get("text") or data.get("generated_text")
        if content:
            return content.strip(), "ai"
        return None, "no_content"
    except Exception as e:
        print("❌ OpenRouter call failed:", e)
        return None, "exception"

# ------------------------
# Smart fallback
# ------------------------
def smart_fallback(message: str) -> str:
    m = message.lower()
    if any(word in m for word in ["leave", "vacation", "time off", "holiday"]):
        return "Employees typically receive 20 vacation days per year. Please submit leave requests through the HR portal at least two weeks in advance."
    if any(word in m for word in ["password", "reset", "login", "account"]):
        return "To reset your password, go to portal.company.com and click 'Forgot Password'. If that doesn't work, reach out to IT at x4357."
    if any(word in m for word in ["software", "install", "program", "application"]):
        return "Submit a software request through the IT Service Catalog with manager approval; typical installs complete within 24 hours."
    return f"I understand you're asking about '{message}'. I can help with HR, IT, events, and document summaries — could you give a bit more detail?"

# ------------------------
# Routes
# ------------------------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ai_connected": bool(OPENROUTER_API_KEY)}), 200

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"success": False, "error": "Empty message"}), 400

        session_id = data.get("session_id") or str(uuid.uuid4())
        if session_id not in sessions:
            sessions[session_id] = []

        # Append user message
        sessions[session_id].append({"role": "user", "text": message, "ts": time.time()})

        # Build short context (last 6 messages)
        context_msgs = sessions[session_id][-6:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in context_msgs:
            role = m.get("role", "user")
            # map to "user" or "assistant" roles expected by model
            if role == "assistant":
                messages.append({"role": "assistant", "content": m.get("text", "")})
            else:
                messages.append({"role": "user", "content": m.get("text", "")})

        # Add the latest user prompt
        messages.append({"role": "user", "content": message})

        # Call OpenRouter/GPT
        ai_text, status = call_openrouter_chat(messages, temperature=0.9, max_tokens=700)
        if not ai_text:
            ai_text = smart_fallback(message)
            response_source = "fallback"
            confidence = 0.45
        else:
            response_source = "ai"
            confidence = 0.9

        # Store assistant reply
        sessions[session_id].append({"role": "assistant", "text": ai_text, "ts": time.time()})

        return jsonify({
            "success": True,
            "response": ai_text,
            "source": response_source,
            "confidence": confidence,
            "session_id": session_id
        })
    except Exception as e:
        print("💥 /api/chat exception:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
def upload():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file part"}), 400
        f = request.files["file"]
        if not f or f.filename == "":
            return jsonify({"success": False, "error": "No selected file"}), 400
        if not allowed_file(f.filename):
            return jsonify({"success": False, "error": "Unsupported file type"}), 400

        filename = secure_filename(f.filename)
        file_bytes = f.read()
        ext = filename.rsplit(".", 1)[1].lower()

        # Extract text depending on extension
        if ext == "pdf":
            if PyPDF2 is None:
                return jsonify({"success": False, "error": "PDF support missing (install PyPDF2)."}), 500
            text = extract_text_from_pdf_bytes(file_bytes)
        else:
            text = extract_text_from_txt_bytes(file_bytes)

        if not text or not text.strip():
            return jsonify({"success": False, "error": "Could not extract text from file."}), 400

        char_count = len(text)
        word_count = len(re.findall(r"\w+", text))

        truncated = False
        if char_count > MAX_PROMPT_CHARS:
            truncated = True
            text_to_send = text[:MAX_PROMPT_CHARS]
            trunc_note = f"\n\n[Document truncated; original length {char_count} characters. Summarize the provided portion and mention it's truncated.]\n"
        else:
            text_to_send = text
            trunc_note = ""

        # Summary prompt
        summary_prompt = (
            "Summarize the document below. Provide:\n"
            "1) A concise title (<=5 words)\n"
            "2) 3-6 bullet points with key facts/insights\n"
            "3) One short suggested action (1 sentence)\n\n"
            "Do not invent facts. If you had to note uncertainty, say so briefly.\n\n"
            "Document:\n\n" + text_to_send + trunc_note
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + " When summarizing, follow the requested structure exactly."},
            {"role": "user", "content": summary_prompt}
        ]

        summary_text, status = call_openrouter_chat(messages, temperature=0.6, max_tokens=700)
        if not summary_text:
            summary_text = "Automatic summary unavailable. Please try again later or upload a shorter file."
            source = "fallback"
        else:
            source = "ai"

        # Keywords extraction (short)
        kw_prompt = (
            "From the document excerpt above, list up to 8 concise keywords or tags, separated by commas."
        )
        kw_messages = [
            {"role": "system", "content": "You are a helpful tag extractor."},
            {"role": "user", "content": kw_prompt + "\n\nExcerpt:\n" + text_to_send[:3000]}
        ]
        kw_text, _ = call_openrouter_chat(kw_messages, temperature=0.3, max_tokens=120)
        keywords = []
        if kw_text:
            candidates = re.split(r"[,\n;]+", kw_text)
            for c in candidates:
                clean = c.strip().lower()
                if clean and clean not in keywords:
                    keywords.append(clean)
                if len(keywords) >= 8:
                    break

        # Save uploaded file (optional)
        try:
            saved_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{int(time.time())}_{filename}")
            with open(saved_path, "wb") as fh:
                fh.write(file_bytes)
        except Exception as e:
            print("⚠️ Could not save file:", e)

        return jsonify({
            "success": True,
            "filename": filename,
            "summary": summary_text,
            "keywords": keywords,
            "word_count": word_count,
            "char_count": char_count,
            "truncated": truncated,
            "source": source
        })
    except Exception as e:
        print("💥 /api/upload exception:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/test", methods=["GET"])
def test():
    test_prompt = "Introduce yourself in a warm, friendly, improvised paragraph (2-4 sentences)."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": test_prompt}
    ]
    text, status = call_openrouter_chat(messages, temperature=0.9, max_tokens=200)
    ok = bool(text)
    return jsonify({"success": ok, "response": text, "status": status})

# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Enterprise Assistant API (OpenRouter + GPT-3.5 Turbo)")
    print("OPENROUTER_URL:", OPENROUTER_URL)
    print("OPENROUTER_MODEL:", OPENROUTER_MODEL)
    print("UPLOAD_FOLDER:", UPLOAD_FOLDER)
    print("PDF parsing available:", PyPDF2 is not None)
    print("AI connected:", bool(OPENROUTER_API_KEY))
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)

