# AI Interview Coach for DevOps Engineers

An interactive interview preparation tool that generates natural, conversational answers for DevOps interview questions. Upload your resume and job description to get personalized coaching.

## Features

- **Natural answers** — AI-generated responses that sound like a real engineer speaking, not a script
- **Resume-aware** — Upload your resume for personalized answers based on your actual experience
- **Job description tailoring** — Upload a JD to align answers with role requirements
- **Voice input** — Speak your questions using the microphone button (Chrome/Edge)
- **Voice playback** — Optional listen button on each answer
- **Streaming responses** — Answers appear token-by-token as they're generated
- **Multiple answer styles** — Natural, Concise, Detailed, Beginner-Friendly
- **Auto-fallback** — If the primary AI provider is unavailable, automatically switches to a backup
- **Interruptible** — Ask a new question anytime; the current response cancels immediately

## Tech Stack

- **Frontend:** Astro + vanilla JS
- **Backend:** Python / FastAPI
- **AI Providers:** Groq (primary), OpenRouter (backup)

## Prerequisites

- Node.js 18+
- Python 3.11+
- An API key from [Groq](https://console.groq.com) (free tier available)

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd int_prep
npm install
cd backend
pip install -r requirements.txt
cd ..
```

### 2. Configure API keys

Copy the example env file and add your keys:

```bash
cp .env.example backend/.env
```

Edit `backend/.env`:

```env
# Primary AI Provider (Groq — required)
OPENAI_API_KEY=gsk_your_groq_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1

# Backup AI Provider (OpenRouter — optional)
BACKUP_OPENAI_API_KEY=sk-or-your_openrouter_key_here
BACKUP_OPENAI_BASE_URL=https://openrouter.ai/api/v1
BACKUP_MODEL=openai/gpt-4o
```

> Get a free Groq API key at https://console.groq.com

### 3. Start the backend

```bash
cd backend
python main.py
```

Runs on http://localhost:8000

### 4. Start the frontend

```bash
npm run dev
```

Runs on http://localhost:4321

Open http://localhost:4321 in your browser.

## Usage

1. **Upload your resume** (PDF/DOCX/TXT) and **job description** for personalized coaching
2. **Type or speak** an interview question
3. The AI generates a natural, conversational answer you can read and practice
4. Use the **Listen** button to hear the answer spoken aloud
5. Try different **answer styles** via the Settings panel (gear icon)

### Answer Styles

| Style | Description |
|---|---|
| Natural | Balanced conversational tone |
| Concise | Short and direct |
| Detailed | Thorough with deeper explanations |
| Beginner-Friendly | Simple language, avoids jargon |

### Voice Input

Click the microphone button to speak your question (supported in Chrome and Edge). The transcript appears in real-time and auto-submits after a pause.

## Project Structure

```
int_prep/
├── backend/
│   ├── main.py          # FastAPI server with all API endpoints
│   └── requirements.txt # Python dependencies
├── src/
│   └── pages/
│       └── index.astro  # Single-page chat application
├── package.json
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/ask` | POST | Generate interview answer (streaming SSE) |
| `/api/upload/resume` | POST | Upload resume |
| `/api/upload/jd` | POST | Upload job description |
| `/api/context/resume` | DELETE | Clear resume context |
| `/api/context/jd` | DELETE | Clear job description context |
| `/api/context` | GET | Check uploaded context status |

## Troubleshooting

- **Blank page / no response** — Make sure the backend is running on port 8000
- **API errors** — Verify your Groq API key in `backend/.env`
- **Voice input not working** — Use Chrome or Edge; grant microphone permission
- **Streaming not working** — Check that `/api/ask` returns SSE (`text/event-stream`)
