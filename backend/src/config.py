"""Project-wide configuration loaded from environment / .env."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "axis_knowledge"


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    Values are sourced from environment variables (or .env if present).
    """

    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    chroma_db_path: Path = Path(os.getenv("CHROMA_DB_PATH", "./.chromadb"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(level: str | None = None) -> None:
    """Configure root logger with project-standard format."""
    logging.basicConfig(
        level=level or Settings().log_level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


settings = Settings()


def load_axes_config(path: Path | None = None) -> dict:
    """Load axes definition from config.yml."""
    import yaml

    config_path = path or Path("./config.yml")
    if not config_path.exists():
        return {"axes": []}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"axes": []}
