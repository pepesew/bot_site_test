import csv
import html
import io
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path


# Кладовка для заявок: простая SQLite-база рядом с ботом
class Kladovka:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                flow TEXT NOT NULL,
                name TEXT,
                phone TEXT,
                estimate INTEGER,
                summary TEXT NOT NULL,
                answers TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                taken_by TEXT
            )
            """
        )
        self.conn.commit()

    def polozhit(self, *, user_id: int, username: str | None, flow: str, name: str,
                 phone: str, estimate: int | None, summary: str, answers: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO leads (created, user_id, username, flow, name, phone, estimate, summary, answers)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                user_id, username, flow, name, phone, estimate, summary,
                json.dumps(answers, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def zapisat_svodku(self, lead_id: int, summary: str) -> None:
        self.conn.execute("UPDATE leads SET summary = ? WHERE id = ?", (summary, lead_id))
        self.conn.commit()

    def vzyat_v_rabotu(self, lead_id: int, kto: str) -> bool:
        cur = self.conn.execute(
            "UPDATE leads SET status = 'work', taken_by = ? WHERE id = ? AND status = 'new'",
            (kto, lead_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def zakryt(self, lead_id: int) -> None:
        self.conn.execute("UPDATE leads SET status = 'done' WHERE id = ?", (lead_id,))
        self.conn.commit()

    def poslednie(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def odna(self, lead_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    def schetchik(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        return {row["status"]: row["n"] for row in rows}

    # Выгрузка всех заявок в CSV, который нормально открывается в Excel (UTF-8 с BOM, разделитель «;»)
    def v_csv(self) -> bytes:
        buf = io.StringIO()
        pisar = csv.writer(buf, delimiter=";")
        pisar.writerow(["№", "Дата", "Направление", "Имя", "Телефон", "Telegram",
                        "Оценка, ₽", "Статус", "Кто взял", "Ответы"])
        statusy = {"new": "Новая", "work": "В работе", "done": "Закрыта"}
        for row in self.conn.execute("SELECT * FROM leads ORDER BY id"):
            pisar.writerow([
                row["id"], row["created"], row["flow"], row["name"], row["phone"],
                f"@{row['username']}" if row["username"] else row["user_id"],
                row["estimate"] or "", statusy.get(row["status"], row["status"]),
                row["taken_by"] or "", html.unescape(re.sub(r"<[^>]+>", "", row["summary"])),
            ])
        return buf.getvalue().encode("utf-8-sig")
