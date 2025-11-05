# Hackathon-Chatbot
## NAME: SHEHAN SHAJAHAN
## REGISTER NO: 212223240154

A lightweight **enterprise assistant** with improvised, human-like AI responses and automatic document summarization.  
Built with **Flask** backend and a simple **HTML/JS frontend**. Supports PDF/TXT uploads with structured summaries.

---

## Features

- **💬 AI Chat**
  - Sends user messages to OpenRouter for warm, conversational replies.
  - Responses are improvised, friendly, and professional.
  - Maintains session history for context.

- **📄 Document Upload & Summarization**
  - Upload `.pdf` or `.txt` files.
  - Automatically generates structured summary:
    - **Title**
    - **3–6 Bullet Points**
    - **Suggested Action**
  - Extracts keywords from documents.
  - Limits upload size to 20 MB.

- **🔗 API Endpoints**
  - `GET /api/health` — check backend and AI connectivity
  - `GET /api/test` — test AI response
  - `POST /api/chat` — send chat message
  - `POST /api/upload` — upload document and get summary

---

## Tech Stack

- **Backend:** Python 3, Flask, Flask-CORS, Requests, PyPDF2 (optional for PDF parsing)  
- **Frontend:** HTML, CSS, JavaScript (vanilla)  
- **AI Provider:** OpenRouter API (or DeepInfra OpenAI-compatible endpoint)  

---

## Setup & Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/enterprise-assistant.git
cd enterprise-assistant
```

2. **Create a virtual environment**
```
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

3. **Install dependencies**
```
pip install -r requirements.txt
```

4. **Set API Key**
Option 1 — Using environment variable (recommended):
```
export OPENROUTER_API_KEY="sk-xxxx"   # macOS/Linux
set OPENROUTER_API_KEY=sk-xxxx        # Windows
````

Option 2 — Directly in app.py (for testing):
```
OPENROUTER_API_KEY = "sk-xxxx"
```

5. **Run the backend**
```
python app.py
```

6. **Open frontend**

Open index.html in a browser. Ensure the API_BASE points to your backend (http://localhost:5000/api).
