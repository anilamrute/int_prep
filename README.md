# AI Interview Coach for DevOps Engineers

An interactive interview prep tool that generates natural, conversational DevOps interview answers. Upload your resume and JD for personalized coaching.

## Features

- **Human-like answers** — Skips dictionary definitions, talks about real experience like an engineer would
- **FAQ question library** — 31 curated DevOps interview questions across 4 categories, searchable and collapsible
- **Resume-aware** — Upload your resume; answers reference your actual projects and skills
- **Job description tailoring** — Upload a JD to align answers with the role
- **Multi-provider fallback** — Groq (primary) → OpenRouter → Local LLM (Ollama), auto-fails over
- **Voice input** — Speak questions via mic (Chrome/Edge); live transcript, auto-submit on silence
- **Mic level meter** — Visual feedback so you know the app hears you
- **Answer length** — Short / Medium / Detailed
- **Streaming responses** — Answers appear as they're generated (batched tokens for speed)
- **Code generation** — Detects Dockerfile vs docker-compose vs K8s YAML vs Terraform vs Bash, outputs proper fenced code blocks
- **Recent questions** — Last 20 stored locally; click to re-ask
- **Interruptible** — New question cancels current response instantly

## Tech Stack

- **Frontend:** Astro + vanilla JS
- **Backend:** Python / FastAPI
- **AI Providers:**
  - Groq (cloud, primary)
  - OpenRouter (cloud, secondary)
  - Ollama / qwen2.5 (local, fallback)

## Prerequisites

- Node.js 18+
- Python 3.11+
- At least one configured AI provider

## Setup

### 1. Install dependencies

```bash
npm install
cd backend && pip install -r requirements.txt && cd ..
```

### 2. Configure API keys

Create `backend/.env`:

```env
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5

# Get a free Groq key at https://console.groq.com
OPENAI_API_KEY=gsk_your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1

BACKUP_OPENAI_API_KEY=sk-or-your_openrouter_key
BACKUP_OPENAI_BASE_URL=https://openrouter.ai/api/v1
BACKUP_MODEL=openai/gpt-4o
```

### 3. (Optional) Local LLM via Ollama

```bash
ollama pull qwen2.5
# or: gemma2, llama3.2, mistral
```

Set `LOCAL_LLM_MODEL` in `backend/.env` to match.

### 4. Start backend

```bash
cd backend && python main.py
```

Runs on http://localhost:8000

### 5. Start frontend

```bash
npm run dev
```

Runs on http://localhost:4321

## Usage

1. **Upload your resume and JD** for personalized answers
2. **Select a model** from the header dropdown (defaults to Groq for speed)
3. **Type, paste, or speak** an interview question
4. **Click a FAQ question** from the sidebar to practice common ones
5. **Adjust answer length** in Settings (Short / Medium / Detailed)
6. **Use 🔄 Try Again** to regenerate, 📋 Copy to copy, ⏹ Stop to cancel

### Voice Input

Click the mic button. Speech appears live in the input and auto-submits after 1.5s of silence. The level meter shows if the mic is picking up audio. If confidence is low, you'll get a prompt to try again.

### Code Questions

Ask for a Dockerfile, docker-compose, K8s YAML, Terraform, or Bash script. The AI outputs a fenced code block with the correct language tag.

## Provider Fallback

1. Selected model → if it fails
2. Next available provider → auto-failover
3. Health checks promote recovered providers

## Project Structure

```
int_prep/
├── backend/
│   ├── main.py              # FastAPI server + prompt logic
│   ├── provider_manager.py  # Fallback orchestration
│   ├── providers/
│   │   ├── base.py          # Abstract AIProvider interface
│   │   ├── gemini.py        # Gemini cloud provider
│   │   ├── grok.py          # Grok/xAI cloud provider
│   │   ├── local.py         # Ollama local provider
│   │   └── openai_compat.py # OpenAI-compatible (Groq/OpenRouter)
│   └── requirements.txt
├── src/
│   └── pages/
│       └── index.astro      # Single-page chat app
├── package.json
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/models` | GET | List available models |
| `/api/ask` | POST | Generate answer (streaming SSE) |
| `/api/upload/resume` | POST | Upload resume |
| `/api/upload/jd` | POST | Upload job description |
| `/api/context/resume` | DELETE | Clear resume |
| `/api/context/jd` | DELETE | Clear job description |
| `/api/context` | GET | Check uploaded context |

## Troubleshooting

- **Blank page** — Is the backend running on port 8000?
- **No models** — Check `backend/.env` has at least one provider configured
- **Local LLM missing** — Is Ollama running? Run `ollama list` to check
- **Slow answers** — Switch to Groq. Local qwen2.5 on CPU is slow (~90s/answer)
- **Voice not working** — Use Chrome/Edge, grant mic permission
- **Resume not used** — Re-upload after backend restart (in-memory sessions)
