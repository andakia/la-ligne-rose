"""Runtime settings, read from environment variables.

An optional `.env` file in the working directory is loaded first (see
`.env.example`). Real environment variables always win over the file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, `#` comments, no interpolation."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Andakia Voice API (external service, not part of this repository)
    api_url: str = "https://api.example.com"
    api_key: str = ""
    api_timeout_s: float = 15.0

    # Telephony
    public_base_url: str = "http://localhost:8080"
    human_transfer_target: str = ""
    max_ai_turns: int = 12
    audio_sample_rate: int = 8000

    # Call journal and privacy
    call_log_path: str = "data/calls.sqlite3"
    caller_hash_salt: str = ""
    log_transcripts: bool = False
    admin_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            api_url=os.getenv("ANDAKIA_API_URL", cls.api_url).rstrip("/"),
            api_key=os.getenv("ANDAKIA_API_KEY", ""),
            api_timeout_s=float(os.getenv("ANDAKIA_API_TIMEOUT_S", cls.api_timeout_s)),
            public_base_url=os.getenv("PUBLIC_BASE_URL", cls.public_base_url).rstrip("/"),
            human_transfer_target=os.getenv("HUMAN_TRANSFER_TARGET", ""),
            max_ai_turns=int(os.getenv("MAX_AI_TURNS", cls.max_ai_turns)),
            audio_sample_rate=int(os.getenv("AUDIO_SAMPLE_RATE", cls.audio_sample_rate)),
            call_log_path=os.getenv("CALL_LOG_PATH", cls.call_log_path),
            caller_hash_salt=os.getenv("CALLER_HASH_SALT", ""),
            log_transcripts=_bool("LOG_TRANSCRIPTS", False),
            admin_token=os.getenv("ADMIN_TOKEN", ""),
        )
