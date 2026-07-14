from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import ENV_PATH, PROFILE_PATH, SITES_PATH


class AzureSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    azure_ai_endpoint: str
    azure_ai_key: str
    azure_ai_deployment: str = "gpt-5.4-mini"
    azure_ai_api_version: str = "2024-10-21"


class Profile(BaseModel):
    target_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_mode: Literal["remote", "hybrid", "onsite", "any"] = "any"
    seniority: Literal["entry", "mid", "senior", "staff", "principal", "any"] = "any"
    salary_floor: int = 0
    preferred_industries: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    min_fit_score: int = Field(default=75, ge=0, le=100)
    daily_application_cap: int = Field(default=15, ge=0)
    circuit_breaker_failures: int = Field(default=3, ge=1)
    # Keyword (matched as a case-insensitive substring of the question label)
    # -> your canned answer, for screening questions with a real factual/
    # legal answer an LLM can't infer from a resume (work authorization,
    # non-competes, salary expectations, etc). Any such question without a
    # matching entry here is left unanswered and the application is not
    # submitted -- see apply/answers.py SENSITIVE_KEYWORDS.
    screening_answers: dict[str, str] = Field(default_factory=dict)


class WhitelistEntry(BaseModel):
    board: Literal["greenhouse", "lever", "github"]
    slug: str


class WebSearchDiscovery(BaseModel):
    enabled: bool = True
    extra_queries: list[str] = Field(default_factory=list)


class DiscoveryConfig(BaseModel):
    web_search: WebSearchDiscovery = Field(default_factory=WebSearchDiscovery)


class SitesConfig(BaseModel):
    whitelist: list[WhitelistEntry] = Field(default_factory=list)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)


def load_profile(path=PROFILE_PATH) -> Profile:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return Profile.model_validate(raw)


def load_sites(path=SITES_PATH) -> SitesConfig:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return SitesConfig.model_validate(raw)


def load_azure_settings() -> AzureSettings:
    return AzureSettings()
