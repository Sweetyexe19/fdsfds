from datetime import datetime
from pathlib import Path

from config import SOLD_EXPORT_DIR

SOLD_ARCHIVE_FILE = SOLD_EXPORT_DIR / "sold_archive.txt"


def append_sold_line(
    login: str,
    password: str,
    backup_email: str,
    backup_password: str,
    twofa_key: str,
    channel_link: str,
    order_id: int | None = None,
) -> None:
    SOLD_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{login}:{password}:{backup_email}:{backup_password}:{twofa_key}:{channel_link}"
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{ts}] [order:{order_id}] " if order_id else f"[{ts}] "
    with open(SOLD_ARCHIVE_FILE, "a", encoding="utf-8") as f:
        f.write(prefix + line + "\n")


def archive_exists() -> bool:
    return SOLD_ARCHIVE_FILE.exists() and SOLD_ARCHIVE_FILE.stat().st_size > 0


def get_archive_path() -> Path:
    return SOLD_ARCHIVE_FILE


def clear_archive() -> None:
    SOLD_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    SOLD_ARCHIVE_FILE.write_text("", encoding="utf-8")
