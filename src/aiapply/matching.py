from __future__ import annotations

from pydantic import BaseModel

from .azure_client import AzureAIClient
from .config import Profile
from .discovery.base import JobPosting
from .resume import ParsedResume

SYSTEM_PROMPT = """You score how well a job posting fits a candidate, given
the candidate's resume and their stated job-search parameters.

Respond with a single JSON object exactly like:
{"fit_score": <0-100 integer>, "reasoning": "<one or two sentences>"}

Score 0 if the posting matches any excluded_keywords or excluded_companies,
or clearly falls outside the candidate's target_titles/locations/work_mode/
seniority. Otherwise weigh title relevance, seniority match, location/work
mode match, and skills overlap. Do not invent candidate qualifications not
present in the resume."""


class FitResult(BaseModel):
    fit_score: int
    reasoning: str


def score_posting(
    client: AzureAIClient,
    posting: JobPosting,
    resume: ParsedResume,
    profile: Profile,
) -> FitResult:
    user_prompt = (
        f"CANDIDATE PROFILE PARAMETERS:\n{profile.model_dump_json(indent=2)}\n\n"
        f"CANDIDATE RESUME:\n{resume.model_dump_json(indent=2)}\n\n"
        f"JOB POSTING:\nTitle: {posting.title}\n"
        f"Company: {posting.company}\nLocation: {posting.location}\n"
        f"Description:\n{posting.description_text[:6000]}"
    )
    result = client.complete_json(SYSTEM_PROMPT, user_prompt)
    return FitResult.model_validate(result)
