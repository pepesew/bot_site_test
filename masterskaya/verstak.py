import html
import re
from typing import Awaitable, Callable

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from masterskaya.knopki import Dver, Tyk
from masterskaya.shkatulka import Shkatulka

Sobytie = Message | CallbackQuery


# Состояние «клиент сейчас что-то пишет руками» (ссылку, комментарий, имя, файл)
class Rabota(StatesGroup):
    pishet = State()


# Отрисовка сообщения: на нажатие кнопки правим текущее сообщение, на текст — шлём новое
async def pokazat_ekran(event: Sobytie, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
            return
        except TelegramBadRequest as oshibka:
            if "message is not modified" in str(oshibka):
                return
        await event.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
    else:
        await event.answer(text, reply_markup=markup, disable_web_page_preview=True)


# Верстак — движок сценария. Он не знает конкретных вопросов: всё берёт из шкатулки
# и ведёт клиента по веткам, запоминая путь (trail), чтобы «Назад» работал из любой точки.
#
# Что лежит в данных FSM:
#   route  — список шагов текущей ветки (с учётом выбранных развилок)
#   trail  — позиции в route, которые клиент реально прошёл (стек для «Назад»)
#   otvety — ответы по id шага
#   flow   — основная ветка (goods/services/promo/...) для сводки и расчёта
#   wait   — что именно сейчас ждём ручным вводом
#   queue  — очередь вариантов мультивыбора, к которым ещё надо спросить пояснение
class Verstak:
    def __init__(self, shk: Shkatulka):
        self.shk = shk
        self.na_finish: Callable[[Sobytie, FSMContext, dict], Awaitable[None]] | None = None
        self.v_menu: Callable[[Sobytie, FSMContext], Awaitable[None]] | None = None

    # Старт ветки из главного меню
    async def nachat(self, event: Sobytie, state: FSMContext, flow: str) -> None:
        await state.set_state(None)
        data = {"route": self.shk.vetka(flow), "trail": [0], "otvety": {}, "flow": flow}
        await state.set_data(data)
        await self._pokazat_shag(event, state, data)

    # Текущий шаг по данным FSM
    def tekushchiy(self, data: dict) -> str | None:
        if not data.get("trail"):
            return None
        return data["route"][data["trail"][-1]]

    # ---------- Отрисовка шагов ----------

    def _shapka(self, shag: dict) -> str:
        chasti = [shag["text"]]
        if shag.get("hint"):
            chasti.append(f"<i>{shag['hint']}</i>")
        if shag.get("footer"):
            chasti.append(shag["footer"])
        return "\n\n".join(chasti)

    def _klava_shaga(self, step_id: str, shag: dict, otvet: dict) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        vybrano = set(otvet.get("picked", []))
        kind = shag["kind"]

        if kind == "single":
            for opt in shag.get("options", []):
                metka = "✔️ " if opt["id"] in vybrano else ""
                kb.button(text=metka + opt["label"], callback_data=Tyk(act="pick", step=step_id, opt=opt["id"]))
        elif kind == "multi":
            for opt in shag.get("options", []):
                metka = "✅ " if opt["id"] in vybrano else "▫️ "
                kb.button(text=metka + opt["label"], callback_data=Tyk(act="tog", step=step_id, opt=opt["id"]))
            kb.button(text=self.shk.knopka("next"), callback_data=Tyk(act="ok", step=step_id))
        elif kind == "sections":
            kategorii = otvet.get("cats", {})
            svoi = otvet.get("custom", {})
            for cat in shag["categories"]:
                skolko = len(kategorii.get(cat["id"], [])) + len(svoi.get(cat["id"], []))
                hvost = f" ({skolko})" if skolko else ""
                kb.button(text=cat["label"] + hvost, callback_data=Tyk(act="cat", step=step_id, cat=cat["id"]))
            inoe = " ✅" if otvet.get("other") else ""
            kb.button(text=self.shk.knopka("other_sections") + inoe, callback_data=Tyk(act="sother", step=step_id))
            kb.button(text=self.shk.knopka("done"), callback_data=Tyk(act="sdone", step=step_id))

        kb.button(text=self.shk.knopka("back"), callback_data=Tyk(act="back", step=step_id))
        kb.adjust(1)
        return kb.as_markup()

    async def _pokazat_shag(self, event: Sobytie, state: FSMContext, data: dict) -> None:
        step_id = self.tekushchiy(data)
        shag = self.shk.shag(step_id)
        otvet = data["otvety"].get(step_id, {})
        tekst = self._shapka(shag)

        if shag["kind"] == "sections" and otvet.get("other"):
            tekst += f"\n\n➕ Иное: <i>{html.escape(otvet['other'])}</i>"

        # Шаги со свободным вводом сразу ждут текст от клиента
        if shag.get("free_input"):
            data["wait"] = {"mode": "free", "step": step_id}
            await state.set_state(Rabota.pishet)
        else:
            data.pop("wait", None)
            await state.set_state(None)
        await state.set_data(data)
        await pokazat_ekran(event, tekst, self._klava_shaga(step_id, shag, otvet))

    async def _sprosit(self, event: Sobytie, state: FSMContext, data: dict, wait: dict, prompt: str) -> None:
        data["wait"] = wait
        await state.set_state(Rabota.pishet)
        await state.set_data(data)
        kb = InlineKeyboardBuilder()
        kb.button(text=self.shk.knopka("back"), callback_data=Tyk(act="cancel", step=wait["step"]))
        await pokazat_ekran(event, prompt, kb.as_markup())

    # ---------- Проверка, что нажата кнопка актуального шага ----------

    async def svezhiy(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> dict | None:
        data = await state.get_data()
        tek = self.tekushchiy(data)
        if tek is None:
            await cb.answer("Начнём сначала 🙂")
            if self.v_menu:
                await self.v_menu(cb, state)
            return None
        if tek != step_id:
            await cb.answer("Этот вопрос уже позади — продолжим с текущего 👇")
            await self._pokazat_shag(cb.message, state, data)
            return None
        return data

    # ---------- Одиночный выбор ----------

    async def vybor(self, cb: CallbackQuery, state: FSMContext, step_id: str, opt_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        opt = self.shk.opciya(step_id, opt_id)
        if opt is None:
            await cb.answer("Вариант больше недоступен")
            await self._pokazat_shag(cb, state, data)
            return
        await cb.answer()
        data["otvety"][step_id] = {"picked": [opt_id], "extra": {}}

        if opt.get("input"):
            await self._sprosit(cb, state, data, {"mode": "opt", "step": step_id, "opt": opt_id}, opt["input"])
        elif opt.get("file"):
            await self._sprosit(cb, state, data, {"mode": "file", "step": step_id, "opt": opt_id}, opt["file"])
        else:
            await self._vpered(cb, state, data, opt.get("flow"))

    # ---------- Мультивыбор ----------

    async def otmetka(self, cb: CallbackQuery, state: FSMContext, step_id: str, opt_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        opt = self.shk.opciya(step_id, opt_id)
        if opt is None:
            await cb.answer()
            return
        otvet = data["otvety"].setdefault(step_id, {"picked": [], "extra": {}})
        vybrano: list = otvet["picked"]

        # «Исключающие» варианты (например «Нет») снимают остальные галочки и наоборот
        if opt_id in vybrano:
            vybrano.remove(opt_id)
        elif opt.get("exclusive"):
            vybrano[:] = [opt_id]
        else:
            isklyuch = {o["id"] for o in self.shk.shag(step_id)["options"] if o.get("exclusive")}
            vybrano[:] = [v for v in vybrano if v not in isklyuch] + [opt_id]

        await cb.answer()
        await state.set_data(data)
        shag = self.shk.shag(step_id)
        try:
            await cb.message.edit_reply_markup(reply_markup=self._klava_shaga(step_id, shag, otvet))
        except TelegramBadRequest:
            pass

    async def dalee(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        otvet = data["otvety"].setdefault(step_id, {"picked": [], "extra": {}})
        if not otvet["picked"]:
            await cb.answer("Выберите хотя бы один вариант ☝️", show_alert=True)
            return
        await cb.answer()

        # Убираем пояснения к снятым галочкам и собираем очередь вопросов-уточнений
        poryadok = [o["id"] for o in self.shk.shag(step_id)["options"]]
        otvet["picked"].sort(key=lambda x: poryadok.index(x) if x in poryadok else 99)
        otvet["extra"] = {k: v for k, v in otvet.get("extra", {}).items() if k in otvet["picked"]}
        data["queue"] = [
            v for v in otvet["picked"]
            if (o := self.shk.opciya(step_id, v)) and (o.get("input") or o.get("file"))
        ]
        await self._sleduyushchee_utochnenie(cb, state, data, step_id)

    async def _sleduyushchee_utochnenie(self, event: Sobytie, state: FSMContext, data: dict, step_id: str) -> None:
        ochered = data.get("queue", [])
        if ochered:
            opt_id = ochered.pop(0)
            opt = self.shk.opciya(step_id, opt_id)
            rezhim = "file" if opt.get("file") else "opt"
            await self._sprosit(event, state, data, {"mode": rezhim, "step": step_id, "opt": opt_id, "multi": True},
                                opt.get("input") or opt.get("file"))
            return
        data.pop("queue", None)
        await self._vpered(event, state, data, self._kuda_prygat(step_id, data))

    # Переход в другую ветку из мультивыбора — только если все отмеченные варианты ведут туда
    def _kuda_prygat(self, step_id: str, data: dict) -> str | None:
        vybrano = data["otvety"].get(step_id, {}).get("picked", [])
        perehody = [(self.shk.opciya(step_id, v) or {}).get("flow") for v in vybrano]
        if perehody and all(perehody):
            return perehody[0]
        return None

    # ---------- Разделы сайта (категории с вложенным мультивыбором) ----------

    def _klava_kategorii(self, step_id: str, cat: dict, otvet: dict) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        vybrano = set(otvet.get("cats", {}).get(cat["id"], []))
        for opt in cat["options"]:
            metka = "✅ " if opt["id"] in vybrano else "▫️ "
            kb.button(text=metka + opt["label"],
                      callback_data=Tyk(act="ctog", step=step_id, cat=cat["id"], opt=opt["id"]))
        if cat.get("custom", True):
            kb.button(text=self.shk.knopka("add_custom"), callback_data=Tyk(act="cadd", step=step_id, cat=cat["id"]))
        kb.button(text=self.shk.knopka("back"), callback_data=Tyk(act="cback", step=step_id))
        kb.adjust(1)
        return kb.as_markup()

    def _tekst_kategorii(self, cat: dict, otvet: dict) -> str:
        tekst = f"<b>{html.escape(cat['label'])}</b>\n\n<i>Множественный выбор — отметьте нужное и нажмите «Назад».</i>"
        svoi = otvet.get("custom", {}).get(cat["id"], [])
        if svoi:
            tekst += "\n\n<b>Ваши варианты:</b>\n" + "\n".join(f"• {html.escape(s)}" for s in svoi)
        return tekst

    async def kategoriya(self, cb: CallbackQuery, state: FSMContext, step_id: str, cat_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        cat = self.shk.kategoriya(step_id, cat_id)
        if cat is None:
            await cb.answer()
            return
        await cb.answer()
        otvet = data["otvety"].setdefault(step_id, {})
        await state.set_state(None)
        data.pop("wait", None)
        await state.set_data(data)
        await pokazat_ekran(cb, self._tekst_kategorii(cat, otvet), self._klava_kategorii(step_id, cat, otvet))

    async def kat_otmetka(self, cb: CallbackQuery, state: FSMContext, step_id: str, cat_id: str, opt_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        cat = self.shk.kategoriya(step_id, cat_id)
        if cat is None:
            await cb.answer()
            return
        otvet = data["otvety"].setdefault(step_id, {})
        vybrano: list = otvet.setdefault("cats", {}).setdefault(cat_id, [])
        if opt_id in vybrano:
            vybrano.remove(opt_id)
        else:
            vybrano.append(opt_id)
        await cb.answer()
        await state.set_data(data)
        try:
            await cb.message.edit_reply_markup(reply_markup=self._klava_kategorii(step_id, cat, otvet))
        except TelegramBadRequest:
            pass

    async def kat_dobavit(self, cb: CallbackQuery, state: FSMContext, step_id: str, cat_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        await cb.answer()
        await self._sprosit(cb, state, data, {"mode": "cat", "step": step_id, "cat": cat_id},
                            "✍️ Напишите свой вариант страницы для этой категории:")

    async def razdely_inoe(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        await cb.answer()
        prompt = self.shk.shag(step_id).get("other_prompt", "✍️ Напишите, какие страницы ещё нужны:")
        await self._sprosit(cb, state, data, {"mode": "sother", "step": step_id}, prompt)

    async def razdely_gotovo(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        otvet = data["otvety"].setdefault(step_id, {})
        nichego = not any(otvet.get("cats", {}).values()) and not any(otvet.get("custom", {}).values()) \
            and not otvet.get("other")
        if nichego:
            await cb.answer("Отметьте хотя бы один раздел ☝️", show_alert=True)
            return
        await cb.answer()
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await cb.message.answer(self.shk.blok("sections_done"))
        await self._vpered(cb.message, state, data)

    # ---------- Назад / отмена ввода ----------

    async def nazad(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        await cb.answer()
        data.pop("queue", None)
        data["trail"].pop()
        if not data["trail"]:
            await state.set_data({})
            if self.v_menu:
                await self.v_menu(cb, state)
            return
        await self._pokazat_shag(cb, state, data)

    async def otmena(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        await cb.answer()
        data.pop("queue", None)
        wait = data.get("wait") or {}
        # Для свободного ввода «Назад» — это шаг назад, для уточнения — возврат к вопросу
        if wait.get("mode") == "free":
            await self.nazad(cb, state, step_id)
            return
        data.pop("wait", None)
        await self._pokazat_shag(cb, state, data)

    async def k_kategoriyam(self, cb: CallbackQuery, state: FSMContext, step_id: str) -> None:
        data = await self.svezhiy(cb, state, step_id)
        if data is None:
            return
        await cb.answer()
        await self._pokazat_shag(cb, state, data)

    # ---------- Приём ручного ввода ----------

    async def prinyat_vvod(self, message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        wait = data.get("wait")
        if not wait or self.tekushchiy(data) != wait.get("step"):
            await state.set_state(None)
            await self.napomnit(message, state)
            return

        step_id = wait["step"]
        rezhim = wait["mode"]
        tekst = (message.text or message.caption or "").strip()

        if rezhim == "file":
            fayl = None
            if message.document:
                fayl = {"id": message.document.file_id, "type": "document", "name": message.document.file_name}
            elif message.photo:
                fayl = {"id": message.photo[-1].file_id, "type": "photo"}
            if not fayl and not tekst:
                await message.answer(self.shk.blok("file_wait"))
                return
            otvet = data["otvety"].setdefault(step_id, {"picked": [wait["opt"]], "extra": {}})
            if fayl:
                otvet["file"] = fayl
            if tekst:
                otvet.setdefault("extra", {})[wait["opt"]] = tekst
            await self._posle_utochneniya(message, state, data, wait)
            return

        if not tekst:
            await message.answer("✍️ Напишите ответ текстом, пожалуйста.")
            return
        tekst = tekst[:1000]

        if rezhim == "opt":
            data["otvety"].setdefault(step_id, {"picked": [wait["opt"]], "extra": {}}) \
                .setdefault("extra", {})[wait["opt"]] = tekst
            await self._posle_utochneniya(message, state, data, wait)

        elif rezhim == "free":
            shag = self.shk.shag(step_id)
            if shag.get("validate") == "phone" and not self.telefon_ok(tekst):
                await message.answer(self.shk.blok("phone_wrong"))
                return
            data["otvety"][step_id] = {"text": tekst}
            data.pop("wait", None)
            await self._vpered(message, state, data)

        elif rezhim == "cat":
            otvet = data["otvety"].setdefault(step_id, {})
            otvet.setdefault("custom", {}).setdefault(wait["cat"], []).append(tekst)
            data.pop("wait", None)
            await state.set_state(None)
            await state.set_data(data)
            cat = self.shk.kategoriya(step_id, wait["cat"])
            await message.answer(self._tekst_kategorii(cat, otvet), reply_markup=self._klava_kategorii(step_id, cat, otvet))

        elif rezhim == "sother":
            data["otvety"].setdefault(step_id, {})["other"] = tekst
            data.pop("wait", None)
            await self._pokazat_shag(message, state, data)

    # Телефон из контакта Telegram (кнопка «поделиться контактом» или пересланная карточка)
    async def prinyat_kontakt(self, message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        wait = data.get("wait") or {}
        shag = self.shk.shag(wait["step"]) if wait.get("step") else {}
        if wait.get("mode") != "free" or shag.get("validate") != "phone":
            await self.napomnit(message, state)
            return
        data["otvety"][wait["step"]] = {"text": message.contact.phone_number}
        data.pop("wait", None)
        await self._vpered(message, state, data)

    async def _posle_utochneniya(self, event: Sobytie, state: FSMContext, data: dict, wait: dict) -> None:
        data.pop("wait", None)
        step_id = wait["step"]
        if wait.get("multi"):
            await self._sleduyushchee_utochnenie(event, state, data, step_id)
        else:
            opt = self.shk.opciya(step_id, wait["opt"]) or {}
            await self._vpered(event, state, data, opt.get("flow"))

    @staticmethod
    def telefon_ok(tekst: str) -> bool:
        if re.search(r"[^\d\s()+\-]", tekst):
            return False
        cifry = re.sub(r"\D", "", tekst)
        return 10 <= len(cifry) <= 15

    # Клиент написал текст, когда бот ждёт нажатия кнопки
    async def napomnit(self, message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        if self.tekushchiy(data) is None:
            if self.v_menu:
                await self.v_menu(message, state)
            return
        await message.answer(self.shk.blok("use_buttons"))
        await self._pokazat_shag(message, state, data)

    # ---------- Движение вперёд ----------

    def _pokazyvat(self, step_id: str, data: dict) -> bool:
        uslovie = self.shk.shag(step_id).get("show_if")
        if not uslovie:
            return True
        vybrano = set(data["otvety"].get(uslovie["step"], {}).get("picked", []))
        return bool(vybrano & set(uslovie["any"]))

    async def _vpered(self, event: Sobytie, state: FSMContext, data: dict, flow: str | None = None) -> None:
        route: list = data["route"]
        pos = data["trail"][-1]
        final = self.shk.vetka("final")

        nxt = pos + 1
        # Прыжок в финал не обрезает ветку — иначе после «Назад» пропущенные вопросы бы потерялись
        if flow == "final":
            if final[0] not in route:
                route.extend(final)
            nxt = route.index(final[0])
        elif flow:
            route = route[:pos + 1] + self.shk.vetka(flow)
            data["flow"] = flow
        data["route"] = route

        while True:
            if nxt >= len(route):
                if final[0] not in route:
                    route.extend(final)
                    continue
                await state.set_state(None)
                data.pop("wait", None)
                await state.set_data(data)
                if self.na_finish:
                    await self.na_finish(event, state, data)
                return
            if self._pokazyvat(route[nxt], data):
                break
            nxt += 1

        data["trail"].append(nxt)
        await self._pokazat_shag(event, state, data)
