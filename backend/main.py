import os
import json
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from PyPDF2 import PdfReader
from docx import Document

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Interview Answer Coach")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

sessions: dict[str, dict] = {}

SYSTEM_PROMPT = """You are a DevOps interview coach. You write answers that sound like a real engineer talking.

OUTPUT:
Question: <user question>
Best Answer: <your answer>

Write like you're explaining to another engineer over coffee. Not like a blog or presentation.

Copy this style — this is what a good answer sounds like:
"So in my current project, I work with Kubernetes pretty regularly. Most of my day-to-day is maintaining deployments and troubleshooting when something goes wrong. I also set up CI/CD pipelines and fix them when they break. Honestly, a lot of it is just figuring out what went wrong and making sure the team can keep shipping."

Never invent anything. If resume says "worked with", say "worked with", not "led". If limited experience, use "I was involved in", "I supported", "I had exposure to"."""

def get_openai_client(api_key=None, base_url=None):
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    base_url = base_url or os.getenv("OPENAI_BASE_URL")
    if not api_key:
        return None
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)

def get_providers(req):
    """Return list of (client, model, label) tuples to try in order."""
    providers = []
    primary = get_openai_client()
    if primary:
        providers.append((primary, req.model, "primary"))
    backup_key = os.getenv("BACKUP_OPENAI_API_KEY")
    backup_base = os.getenv("BACKUP_OPENAI_BASE_URL")
    backup_model = os.getenv("BACKUP_MODEL", "openai/gpt-4o")
    if backup_key:
        backup = get_openai_client(api_key=backup_key, base_url=backup_base)
        if backup:
            providers.append((backup, backup_model, "backup"))
    return providers

def extract_text_from_pdf(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""

def extract_text_from_docx(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return ""

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/upload/resume")
async def upload_resume(session_id: str = "default", file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(400, "Only PDF, DOCX, and TXT files are supported.")
    path = str(UPLOAD_DIR / f"{session_id}_resume{ext}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    if ext == ".pdf":
        text = extract_text_from_pdf(path)
    elif ext == ".docx":
        text = extract_text_from_docx(path)
    else:
        text = content.decode("utf-8", errors="ignore")
    if session_id not in sessions:
        sessions[session_id] = {}
    sessions[session_id]["resume"] = text[:15000]
    return {"status": "ok", "preview": text[:300]}

@app.post("/api/upload/jd")
async def upload_jd(session_id: str = "default", file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(400, "Only PDF, DOCX, and TXT files are supported.")
    path = str(UPLOAD_DIR / f"{session_id}_jd{ext}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    if ext == ".pdf":
        text = extract_text_from_pdf(path)
    elif ext == ".docx":
        text = extract_text_from_docx(path)
    else:
        text = content.decode("utf-8", errors="ignore")
    if session_id not in sessions:
        sessions[session_id] = {}
    sessions[session_id]["jd"] = text[:15000]
    return {"status": "ok", "preview": text[:300]}

@app.delete("/api/context/resume")
def clear_resume(session_id: str = "default"):
    if session_id in sessions:
        sessions[session_id].pop("resume", None)

@app.delete("/api/context/jd")
def clear_jd(session_id: str = "default"):
    if session_id in sessions:
        sessions[session_id].pop("jd", None)

class AskRequest(BaseModel):
    question: str
    session_id: str = "default"
    model: str = "llama-3.3-70b-versatile"
    style: str = "natural"

@app.post("/api/ask")
def ask(req: AskRequest):
    session = sessions.get(req.session_id, {})
    resume_text = session.get("resume", "")
    jd_text = session.get("jd", "")
    context_parts = [SYSTEM_PROMPT]
    if resume_text:
        context_parts.append(f"\nUSER'S RESUME CONTEXT:\n{resume_text}\n\nUse this experience to personalize answers. Reference real projects and skills.")
    if jd_text:
        context_parts.append(f"\nJOB DESCRIPTION CONTEXT:\n{jd_text}\n\nTailor answers to this role. Prioritize mentioned technologies and seniority level.")
    system = "\n".join(context_parts)

    style_guides = {
        "natural": "\nSTYLE: Answer in a natural, conversational tone — as if speaking directly to the candidate. Balance depth with clarity.",
        "concise": "\nSTYLE: Keep it short and direct. Aim for 80-120 words. Get straight to the point. Use plain, simple sentences.",
        "detailed": "\nSTYLE: Be thorough and detailed. Provide deep explanations, multiple examples, and comprehensive coverage of the topic. 2-3 paragraphs per section is fine.",
        "beginner": "\nSTYLE: Explain as if the candidate is new to DevOps. Avoid jargon without explanation. Use simple analogies. Break down concepts step by step. Be encouraging and patient.",
    }
    style_instruction = style_guides.get(req.style, style_guides["natural"])
    system += style_instruction

    providers = get_providers(req)
    if not providers:
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'No AI providers configured. Set API keys in .env'})}\n\n"]),
            media_type="text/event-stream",
        )

    def generate():
        switched = False
        for idx, (client, model, label) in enumerate(providers):
            if idx > 0 and not switched:
                switched = True
                yield f"data: {json.dumps({'token': '[Switching to backup AI service...]'})}\n\n"
            try:
                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": req.question},
                    ],
                    temperature=0.9,
                    max_tokens=2048,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield f"data: {json.dumps({'token': delta})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            except Exception as e:
                err_str = str(e)
                if "402" in err_str or "insufficient credits" in err_str.lower() or "payment required" in err_str.lower():
                    logger.warning(f"Provider {label} returned 402, trying next...")
                    continue
                yield f"data: {json.dumps({'error': err_str})}\n\n"
                return
        yield f"data: {json.dumps({'error': 'All AI providers failed. Please check your API keys.'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/context")
def get_context(session_id: str = "default"):
    session = sessions.get(session_id, {})
    return {
        "has_resume": "resume" in session,
        "has_jd": "jd" in session,
        "resume_preview": (session.get("resume", "") or "")[:200],
        "jd_preview": (session.get("jd", "") or "")[:200],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
