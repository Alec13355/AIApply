from __future__ import annotations

from ..azure_client import AzureAIClient
from ..config import Profile
from ..discovery.base import JobPosting
from ..resume import ParsedResume

# Questions matching these are never answered by the LLM or guessed -- they
# ask the candidate to voluntarily self-identify protected characteristics.
# The form should be left as "Decline to self-identify" (or left blank if no
# such option exists), never inferred.
DEMOGRAPHIC_KEYWORDS = [
    "gender", "race", "ethnicity", "hispanic", "latino", "veteran",
    "disability", "sexual orientation", "pronoun",
]

# Questions matching these have a real factual/legal answer (work
# authorization, non-competes, comp expectations, prior employment, etc.)
# that cannot be inferred from a resume. These are only answered from an
# explicit profile.yaml `screening_answers` entry; if none matches, the
# application is not submitted.
SENSITIVE_KEYWORDS = [
    "visa", "sponsorship", "work authoriz", "authorized to work",
    "non-compete", "noncompete", "employment agreement", "restrictive covenant",
    "background check", "drug test", "felony", "convicted",
    "salary expect", "compensation expect", "desired salary",
    "previously worked", "previously employed", "relative", "nepotism",
    "security clearance", "citizenship", "relocat",
    "country of residence", "current country", "current location",
]

SYSTEM_PROMPT = """You write a candidate's answer to a job application's
free-text question. Ground the answer strictly in the provided resume. Do
not invent facts, dates, employers, or skills not present in the resume.
Keep answers concise (1-4 sentences unless the question clearly wants a
list). If the question can't be answered truthfully from the resume, say so
briefly and honestly instead of inventing an answer.

Respond with a single JSON object: {"answer": "<the answer text>"}"""


def classify_question(label: str) -> str:
    low = label.lower()
    if any(k in low for k in DEMOGRAPHIC_KEYWORDS):
        return "demographic"
    if any(k in low for k in SENSITIVE_KEYWORDS):
        return "sensitive"
    return "open"


def screening_answer(label: str, profile: Profile) -> str | None:
    low = label.lower()
    for keyword, answer in profile.screening_answers.items():
        if keyword.lower() in low:
            return answer
    return None


def generate_open_answer(
    client: AzureAIClient,
    question: str,
    resume: ParsedResume,
    posting: JobPosting,
) -> str:
    user_prompt = (
        f"QUESTION: {question}\n\n"
        f"RESUME:\n{resume.model_dump_json(indent=2)}\n\n"
        f"JOB TITLE: {posting.title} at {posting.company}"
    )
    result = client.complete_json(SYSTEM_PROMPT, user_prompt)
    return result.get("answer", "")


def generate_cover_letter(
    client: AzureAIClient,
    resume: ParsedResume,
    posting: JobPosting,
) -> str:
    system = (
        "Write a concise, factual cover letter (under 250 words) for this "
        "candidate applying to this job. Ground every claim strictly in the "
        "resume -- do not invent experience, employers, or skills. "
        "Respond with a single JSON object: {\"cover_letter\": \"...\"}"
    )
    user_prompt = (
        f"RESUME:\n{resume.model_dump_json(indent=2)}\n\n"
        f"JOB TITLE: {posting.title} at {posting.company}\n"
        f"JOB DESCRIPTION:\n{posting.description_text[:4000]}"
    )
    result = client.complete_json(system, user_prompt)
    return result.get("cover_letter", "")
