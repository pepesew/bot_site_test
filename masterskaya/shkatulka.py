import json
import shutil
from datetime import datetime
from pathlib import Path


# Шкатулка со всем содержимым бота: тексты, кнопки, шаги сценария, портфолио, цены.
# Всё лежит в одном JSON — админ меняет его через бота, а бот сразу работает по-новому.
class Shkatulka:
    def __init__(self, path: Path):
        self.path = path
        self.dannye: dict = {}
        self.perechitat()

    def perechitat(self) -> None:
        with self.path.open(encoding="utf-8") as f:
            self.dannye = json.load(f)
        self._proverit()

    # Перед записью кладём копию старой версии в папку backups — на случай неудачной правки
    def sohranit(self) -> None:
        zapas = self.path.parent / "backups"
        zapas.mkdir(exist_ok=True)
        metka = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(self.path, zapas / f"scenario_{metka}.json")
        starye = sorted(zapas.glob("scenario_*.json"))
        for lishniy in starye[:-30]:
            lishniy.unlink()

        vremenny = self.path.with_suffix(".tmp")
        with vremenny.open("w", encoding="utf-8") as f:
            json.dump(self.dannye, f, ensure_ascii=False, indent=2)
        vremenny.replace(self.path)

    # Проверка, что все шаги из веток реально описаны — ловим опечатки сразу при запуске
    def _proverit(self) -> None:
        shagi = self.dannye["steps"]
        for vetka, spisok in self.dannye["flows"].items():
            for shag in spisok:
                if shag not in shagi:
                    raise ValueError(f"Ветка «{vetka}» ссылается на несуществующий шаг «{shag}»")
        for shag_id, shag in shagi.items():
            for opt in shag.get("options", []):
                if opt.get("flow") and opt["flow"] not in self.dannye["flows"]:
                    raise ValueError(f"Шаг «{shag_id}»: неизвестная ветка «{opt['flow']}»")

    # Быстрый доступ к частям шкатулки
    def blok(self, key: str) -> str:
        return self.dannye["blocks"][key]["text"]

    def knopka(self, key: str) -> str:
        return self.dannye["buttons"][key]

    def shag(self, step_id: str) -> dict:
        return self.dannye["steps"][step_id]

    def vetka(self, flow: str) -> list[str]:
        return list(self.dannye["flows"][flow])

    def nazvanie_vetki(self, flow: str) -> str:
        return self.dannye.get("flow_titles", {}).get(flow, flow)

    def opciya(self, step_id: str, opt_id: str) -> dict | None:
        for opt in self.shag(step_id).get("options", []):
            if opt["id"] == opt_id:
                return opt
        return None

    def kategoriya(self, step_id: str, cat_id: str) -> dict | None:
        for cat in self.shag(step_id).get("categories", []):
            if cat["id"] == cat_id:
                return cat
        return None

    def sfera(self, sphere_id: str) -> dict | None:
        for sfera in self.dannye["portfolio"]:
            if sfera["id"] == sphere_id:
                return sfera
        return None

    @property
    def nastroyka(self) -> dict:
        return self.dannye.setdefault("settings", {})
