import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

KOREN = Path(__file__).resolve().parent.parent


# Читаем .env и собираем всё, что задаётся при запуске (токен, админы, пути к файлам)
@dataclass
class Nastroyki_epta:
    token: str
    admin_ids: set[int] = field(default_factory=set)
    scenario_path: Path = KOREN / "content" / "scenario.json"
    db_path: Path = KOREN / "data" / "zayavki.sqlite3"

    @classmethod
    def iz_env(cls) -> "Nastroyki_epta":
        load_dotenv(KOREN / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("Не задан BOT_TOKEN в файле .env")
        admins = {
            int(chunk)
            for chunk in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",")
            if chunk.lstrip("-").isdigit()
        }
        return cls(token=token, admin_ids=admins)
