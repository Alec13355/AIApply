from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

PROFILE_PATH = CONFIG_DIR / "profile.yaml"
SITES_PATH = CONFIG_DIR / "sites.yaml"
ENV_PATH = ROOT / ".env"

RESUME_PATH = DATA_DIR / "resume.pdf"
RESUME_CACHE_PATH = DATA_DIR / "resume_parsed.json"
STORE_PATH = DATA_DIR / "store.db"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
