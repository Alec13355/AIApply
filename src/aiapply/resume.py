from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field
from pypdf import PdfReader
from docx import Document

from .azure_client import AzureAIClient
from .paths import RESUME_CACHE_PATH, RESUME_PATH, ensure_data_dir

SYSTEM_PROMPT = """You extract structured data from a resume's raw text.
Respond with a single JSON object matching this shape exactly:
{
  "name": string,
  "email": string,
  "phone": string,
  "location": string,
  "links": {"linkedin": string|null, "github": string|null, "portfolio": string|null},
  "summary": string,
  "skills": [string],
  "experience": [
    {"company": string, "title": string, "start_date": string, "end_date": string, "bullets": [string]}
  ],
  "education": [
    {"school": string, "degree": string, "field": string, "graduation_date": string}
  ],
  "certifications": [string]
}
Only use information present in the resume text. Do not invent experience,
dates, or skills that aren't there. Use "" for unknown string fields and []
for unknown list fields."""


class Links(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class Experience(BaseModel):
    company: str
    title: str
    start_date: str = ""
    end_date: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str
    degree: str = ""
    field: str = ""
    graduation_date: str = ""


class ParsedResume(BaseModel):
    name: str
    email: str
    phone: str = ""
    location: str = ""
    links: Links = Field(default_factory=Links)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported resume format: {suffix} (use .pdf or .docx)")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_resume(
    client: AzureAIClient,
    resume_path: Path = RESUME_PATH,
    cache_path: Path = RESUME_CACHE_PATH,
    force: bool = False,
) -> ParsedResume:
    if not resume_path.exists():
        raise FileNotFoundError(
            f"No resume found at {resume_path}. Copy your resume (.pdf or .docx) there."
        )

    ensure_data_dir()
    file_hash = _file_hash(resume_path)

    if not force and cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("_source_hash") == file_hash:
            return ParsedResume.model_validate(cached["resume"])

    text = _extract_text(resume_path)
    result = client.complete_json(SYSTEM_PROMPT, text)
    parsed = ParsedResume.model_validate(result)

    cache_path.write_text(
        json.dumps({"_source_hash": file_hash, "resume": parsed.model_dump()}, indent=2)
    )
    return parsed
