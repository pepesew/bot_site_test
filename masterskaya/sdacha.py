import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from masterskaya.kladovka import Kladovka
from masterskaya.knopki import Knopki_epta
from masterskaya.shkatulka import Shkatulka

log = logging.getLogger(__name__)


# Раскрой — превращает сырые ответы из FSM в читаемую сводку для менеджера
class Raskroy:
    def __init__(self, shk: Shkatulka):
        self.shk = shk

    def projdennye(self, data: dict) -> list[str]:
        uvideno: list[str] = []
        for pos in data.get("trail", []):
            step_id = data["route"][pos]
            if step_id not in uvideno:
                uvideno.append(step_id)
        return uvideno

    def otvet_tekstom(self, step_id: str, otvet: dict) -> str:
        shag = self.shk.shag(step_id)
        if "text" in otvet:
            return html.escape(otvet["text"])

        if shag["kind"] == "sections":
            stroki = []
            for cat in shag["categories"]:
                nazvaniya = [o["label"] for o in cat["options"] if o["id"] in otvet.get("cats", {}).get(cat["id"], [])]
                nazvaniya += otvet.get("custom", {}).get(cat["id"], [])
                if nazvaniya:
                    stroki.append(f"  ▸ {html.escape(cat['label'])}: {html.escape(', '.join(nazvaniya))}")
            if otvet.get("other"):
                stroki.append(f"  ▸ Иное: {html.escape(otvet['other'])}")
            return "\n" + "\n".join(stroki) if stroki else "—"

        kuski = []
        for opt_id in otvet.get("picked", []):
            opt = self.shk.opciya(step_id, opt_id)
            kusok = html.escape(opt["label"] if opt else opt_id)
            poyasnenie = otvet.get("extra", {}).get(opt_id)
            if poyasnenie:
                kusok += f" — «{html.escape(poyasnenie)}»"
            kuski.append(kusok)
        if otvet.get("file"):
            kuski.append("📎 файл приложен ниже")
        return ", ".join(kuski) or "—"

    def svodka(self, data: dict) -> str:
        final = set(self.shk.vetka("final"))
        stroki = []
        for step_id in self.projdennye(data):
            if step_id in final:
                continue
            otvet = data["otvety"].get(step_id)
            if otvet is None:
                continue
            zagolovok = html.escape(self.shk.shag(step_id).get("title", step_id))
            stroki.append(f"<b>{zagolovok}:</b> {self.otvet_tekstom(step_id, otvet)}")
        return "\n".join(stroki)

    def kontakt(self, data: dict, step_id: str) -> str:
        otvet = data["otvety"].get(step_id)
        return self.otvet_tekstom(step_id, otvet) if otvet else "—"


# Смета — ориентировочный расчёт стоимости по ответам (доп. функция)
# База берётся по ветке, к ней прибавляются цены отмеченных вариантов и страницы из «Разделов сайта»
class Smeta:
    def __init__(self, shk: Shkatulka, raskroy: Raskroy):
        self.shk = shk
        self.raskroy = raskroy

    def poschitat(self, data: dict) -> int | None:
        if not self.shk.nastroyka.get("estimate_enabled", True):
            return None
        cennik = self.shk.dannye.get("estimate", {})
        baza = cennik.get("base", {}).get(data.get("flow"))
        if baza is None:
            return None

        itogo = int(baza)
        za_stranicu = int(cennik.get("per_section", 0))
        for step_id in self.raskroy.projdennye(data):
            otvet = data["otvety"].get(step_id, {})
            shag = self.shk.shag(step_id)
            if shag["kind"] == "sections":
                stranic = sum(len(v) for v in otvet.get("cats", {}).values())
                stranic += sum(len(v) for v in otvet.get("custom", {}).values())
                itogo += stranic * za_stranicu
                continue
            for opt_id in otvet.get("picked", []):
                opt = self.shk.opciya(step_id, opt_id) or {}
                itogo += int(opt.get("price", 0))
        return itogo

    @staticmethod
    def krasivo(summa: int) -> str:
        return f"{summa:,}".replace(",", " ")


# Сдача заказа: сохраняем заявку, отправляем менеджеру и благодарим клиента
class Sdacha:
    def __init__(self, bot: Bot, shk: Shkatulka, kladovka: Kladovka, knopki: Knopki_epta, admin_ids: set[int]):
        self.bot = bot
        self.shk = shk
        self.kladovka = kladovka
        self.knopki = knopki
        self.admin_ids = admin_ids
        self.raskroy = Raskroy(shk)
        self.smeta = Smeta(shk, self.raskroy)

    # Куда слать заявки: в назначенный чат менеджеров, иначе — всем админам в личку
    def adresaty(self) -> list[int]:
        chat = self.shk.nastroyka.get("manager_chat_id")
        return [int(chat)] if chat else sorted(self.admin_ids)

    def kartochka(self, lead_id: int, data: dict, user, summa: int | None) -> str:
        imya = self.raskroy.kontakt(data, "f_name")
        tg = f"@{html.escape(user.username)}" if user.username else "без username"
        stroki = [
            f"🔔 <b>Новая заявка #{lead_id}</b>",
            f"📂 {html.escape(self.shk.nazvanie_vetki(data.get('flow', '')))}",
            "",
            f"👤 <b>Имя:</b> {imya}",
            f"📱 <b>Телефон:</b> {self.raskroy.kontakt(data, 'f_phone')}",
            f"💬 <b>Мессенджеры:</b> {self.raskroy.kontakt(data, 'f_msg')}",
            f"🕒 <b>Когда связаться:</b> {self.raskroy.kontakt(data, 'f_time')}",
            f"✈️ <b>Telegram:</b> <a href=\"tg://user?id={user.id}\">{tg}</a>",
            "",
            "<b>Ответы:</b>",
            self.raskroy.svodka(data) or "—",
        ]
        if summa is not None:
            stroki += ["", f"💰 <b>Ориентировочная оценка:</b> от {self.smeta.krasivo(summa)} ₽"]
        return "\n".join(stroki)

    async def otpravit_menedzheru(self, tekst: str, markup=None, fayly: list[dict] | None = None) -> None:
        kuski = self.narezat(tekst)
        for chat_id in self.adresaty():
            try:
                for i, kusok in enumerate(kuski):
                    await self.bot.send_message(chat_id, kusok, reply_markup=markup if i == len(kuski) - 1 else None,
                                                disable_web_page_preview=True)
                for fayl in fayly or []:
                    if fayl["type"] == "photo":
                        await self.bot.send_photo(chat_id, fayl["id"], caption=fayl.get("caption"))
                    else:
                        await self.bot.send_document(chat_id, fayl["id"], caption=fayl.get("caption"))
            except TelegramAPIError as oshibka:
                log.warning("Не удалось отправить заявку в чат %s: %s", chat_id, oshibka)

    # Телеграм не пропускает сообщения длиннее 4096 символов — режем по строкам
    @staticmethod
    def narezat(tekst: str, limit: int = 4000) -> list[str]:
        kuski, tekushchiy = [], ""
        for stroka in tekst.split("\n"):
            if len(tekushchiy) + len(stroka) + 1 > limit and tekushchiy:
                kuski.append(tekushchiy)
                tekushchiy = ""
            tekushchiy += stroka + "\n"
        if tekushchiy:
            kuski.append(tekushchiy)
        return kuski

    async def __call__(self, event: Message | CallbackQuery, state: FSMContext, data: dict) -> None:
        user = event.from_user
        message = event.message if isinstance(event, CallbackQuery) else event
        summa = self.smeta.poschitat(data)
        imya = data["otvety"].get("f_name", {}).get("text", "")

        # Сохраняем заявку в базе и отправляем карточку менеджеру
        lead_id = self.kladovka.polozhit(
            user_id=user.id,
            username=user.username,
            flow=self.shk.nazvanie_vetki(data.get("flow", "")),
            name=imya,
            phone=data["otvety"].get("f_phone", {}).get("text", ""),
            estimate=summa,
            summary="",
            answers=data,
        )
        kartochka = self.kartochka(lead_id, data, user, summa)
        self.kladovka.zapisat_svodku(lead_id, kartochka)

        fayly = []
        for step_id in self.raskroy.projdennye(data):
            fayl = data["otvety"].get(step_id, {}).get("file")
            if fayl:
                fayly.append({**fayl, "caption": f"📎 ТЗ к заявке #{lead_id}"})
        await self.otpravit_menedzheru(kartochka, self.knopki.lid(lead_id), fayly)

        # Благодарим клиента и показываем оценку, если она посчитана
        tekst = self.shk.blok("final_thanks").replace("{name}", html.escape(imya))
        if summa is not None:
            tekst += "\n\n" + self.shk.blok("estimate").replace("{sum}", self.smeta.krasivo(summa))
        await state.clear()
        if isinstance(event, CallbackQuery):
            try:
                await message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                pass
        await message.answer(tekst, reply_markup=self.knopki.posle_zayavki(), disable_web_page_preview=True)
