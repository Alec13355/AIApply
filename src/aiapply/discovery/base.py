from __future__ import annotations

from pydantic import BaseModel


class JobPosting(BaseModel):
    board: str  # "greenhouse" | "lever" | "web" | "github"
    company: str
    external_id: str
    title: str
    location: str = ""
    url: str
    description_text: str = ""
    auto_apply_eligible: bool = False

    @property
    def posting_key(self) -> str:
        return f"{self.board}:{self.company}:{self.external_id}"
