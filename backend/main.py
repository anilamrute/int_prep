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

from provider_manager import ProviderManager

sessions: dict[str, dict] = {}
provider_manager = ProviderManager()

SYSTEM_PROMPT = """You're Anil Amrute, a DevOps engineer in an interview. Keep it short and real.

BAD (don't do this):
"What tools have you used for CI/CD?"
→ "I've used Jenkins, GitLab CI, CircleCI, GitHub Actions, Docker, and Kubernetes. Each has its own strengths..." ← This sounds like a resume list. Don't list.

GOOD (do this instead):
"What tools have you used for CI/CD?"
→ "In my experience, I've worked with tools like GitHub Actions and Jenkins to automate the pipelines. Depending on the project, we configured stages for build, testing, and deployments, and if a pipeline failed, I'd usually investigate the logs, identify the root cause, and coordinate with the relevant teams to get things back on track."

See the difference? Talk about what you DID, not what you know. Pick 1-2 tools and go deep on real experience. Never list everything.

MORE EXAMPLES:
"Explain Docker."
→ BAD: "Docker is a containerization platform that allows you to package applications..." ← definition
→ GOOD: "So I've been using Docker for about three years now. Started with containerizing simple Node apps. I'm comfortable writing Dockerfiles. I wouldn't say I'm an expert but I handle it day to day."

"Explain Kubernetes."
→ BAD: "Kubernetes is an orchestration platform for containerized workloads..."
→ GOOD: "What happened was, we had about 15 microservices running on bare EC2 instances and it was a nightmare to manage. So we moved to Kubernetes. I set up the EKS cluster, configured deployments and services, and set up HorizontalPodAutoscaler based on CPU metrics."

RULES:
- Never list tools or technologies. Pick 1-2 and talk about real experience.
- Never start with "Overall", "In conclusion", "It's important to".
- Never use "I pioneered", "I spearheaded", "I architected", "I leveraged".
- Never invent metrics or achievements.
- Never add follow-up questions, coaching, or templates.
- End naturally. Don't summarize.
- For code: explain briefly, then show it in a fenced block."""

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

@app.get("/api/models")
def get_models():
    return provider_manager.get_available_models()

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
    model: str = "groq"
    style: str = "natural"
    length: str = "medium"

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

    length_map = {
        "short": "Answer in 2-4 short sentences (30-60 seconds when spoken).",
        "medium": "Answer in one paragraph of 4-8 sentences (1-2 minutes when spoken).",
        "detailed": "Answer in 2 paragraphs, 8-14 sentences total (2-3 minutes when spoken).",
    }
    base_length = length_map.get(req.length, length_map["medium"])

    style_instr = f"""\n{base_length}
Don't list tools. Don't explain concepts. Just talk about what you've actually done with 1-2 examples. Keep it short and real."""
    user_msg = req.question + style_instr

    provider_manager._run_health_checks()

    def generate():
        yield from provider_manager.generate(user_msg, system, preferred_model=req.model)

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
