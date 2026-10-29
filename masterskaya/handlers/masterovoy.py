import html
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from masterskaya.kladovka import Kladovka
from masterskaya.knopki import Knopki_epta, Lid, Pravka
from masterskaya.nastroyki import Nastroyki_epta
from masterskaya.sdacha import Sdacha
from masterskaya.shkatulka import Shkatulka
from masterskaya.verstak import Sobytie, pokazat_ekran

router = Router(name="masterovoy")


# Пускаем в админку только тех, кто указан в ADMIN_IDS
class Svoy_chelovek(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, nastroyki: Nastroyki_epta) -> bool:
        return event.from_user is not None and event.from_user.id in nastroyki.admin_ids


class Masterovoy(StatesGroup):
    zhdu = State()


STATUSY = {"new": "🆕 Новая", "work": "🙋 В работе", "done": "✅ Закрыта"}


def _kb(*ryady: tuple[str, Pravka]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for tekst, cd in ryady:
        kb.button(text=tekst, callback_data=cd)
    kb.adjust(1)
    return kb.as_markup()


def _nazad(act: str = "menu", key: str = "", sub: str = "") -> tuple[str, Pravka]:
    return "⬅️ Назад", Pravka(act=act, key=key, sub=sub)


# Вариант ответа может лежать прямо в шаге или внутри категории «Разделов сайта» (sub = "кат/вариант")
def najti_opciyu(shk: Shkatulka, step_id: str, sub: str) -> dict | None:
    if "/" in sub:
        cat_id, opt_id = sub.split("/", 1)
        cat = shk.kategoriya(step_id, cat_id) or {}
        return next((o for o in cat.get("options", []) if o["id"] == opt_id), None)
    return shk.opciya(step_id, sub)


def poryadok_shagov(shk: Shkatulka) -> list[str]:
    uvideno: list[str] = []
    for spisok in shk.dannye["flows"].values():
        for step_id in spisok:
            if step_id not in uvideno:
                uvideno.append(step_id)
    return uvideno


# ---------- Экраны админки ----------

async def glavnyy_ekran(event: Sobytie, kladovka: Kladovka) -> None:
    schet = kladovka.schetchik()
    tekst = (
        "🛠 <b>Панель управления ботом</b>\n\n"
        f"Заявок: новых — {schet.get('new', 0)}, в работе — {schet.get('work', 0)}, "
        f"закрытых — {schet.get('done', 0)}\n\n"
        "Выберите, что хотите изменить. Все правки применяются сразу, без перезапуска."
    )
    await pokazat_ekran(event, tekst, _kb(
        ("📝 Тексты и информационные блоки", Pravka(act="blocks")),
        ("🔘 Надписи на кнопках меню", Pravka(act="buttons")),
        ("❓ Вопросы и варианты ответов", Pravka(act="steps")),
        ("🗂 Примеры работ (портфолио)", Pravka(act="pf")),
        ("💰 Расчёт стоимости", Pravka(act="price")),
        ("📥 Последние заявки", Pravka(act="leads")),
        ("📤 Выгрузить заявки в Excel", Pravka(act="csv")),
        ("⚙️ Куда приходят заявки", Pravka(act="chat")),
    ))


async def ekran_blokov(event: Sobytie, shk: Shkatulka) -> None:
    ryady = [(b["title"], Pravka(act="blk", key=k)) for k, b in shk.dannye["blocks"].items()]
    await pokazat_ekran(event, "📝 <b>Тексты и информационные блоки</b>\n\nВыберите блок:", _kb(*ryady, _nazad()))


async def ekran_bloka(event: Sobytie, shk: Shkatulka, key: str) -> None:
    blok = shk.dannye["blocks"][key]
    tekst = f"📝 <b>{html.escape(blok['title'])}</b>\n\nСейчас клиент видит:\n━━━━━━━━━━\n{blok['text']}\n━━━━━━━━━━"
    await pokazat_ekran(event, tekst, _kb(
        ("✏️ Изменить текст", Pravka(act="edit", key="block", sub=key)),
        _nazad("blocks"),
    ))


async def ekran_knopok(event: Sobytie, shk: Shkatulka) -> None:
    ryady = [(nadpis, Pravka(act="edit", key="button", sub=k)) for k, nadpis in shk.dannye["buttons"].items()]
    await pokazat_ekran(event, "🔘 <b>Надписи на кнопках</b>\n\nНажмите на кнопку, чтобы переименовать её:",
                        _kb(*ryady, _nazad()))


async def ekran_shagov(event: Sobytie, shk: Shkatulka) -> None:
    ryady = [(shk.shag(s).get("title", s), Pravka(act="st", key=s)) for s in poryadok_shagov(shk)]
    await pokazat_ekran(event, "❓ <b>Вопросы анкеты</b>\n\nВыберите вопрос:", _kb(*ryady, _nazad()))


async def ekran_shaga(event: Sobytie, shk: Shkatulka, step_id: str) -> None:
    shag = shk.shag(step_id)
    tekst = f"❓ <b>{html.escape(shag.get('title', step_id))}</b>\n\n{shag['text']}"
    if shag.get("hint"):
        tekst += f"\n<i>{shag['hint']}</i>"
    ryady = [
        ("✏️ Текст вопроса", Pravka(act="edit", key="st_text", sub=step_id)),
        ("✏️ Подсказка под вопросом", Pravka(act="edit", key="st_hint", sub=step_id)),
    ]
    if shag["kind"] == "sections":
        tekst += "\n\nКатегории разделов — нажмите, чтобы изменить варианты внутри:"
        ryady += [(f"📂 {c['label']}", Pravka(act="cat", key=step_id, sub=c["id"])) for c in shag["categories"]]
    else:
        if shag.get("options"):
            tekst += "\n\nВарианты ответа — нажмите, чтобы изменить:"
        for opt in shag.get("options", []):
            cena = f"  · +{opt['price']} ₽" if opt.get("price") else ""
            ryady.append((f"🔘 {opt['label']}{cena}", Pravka(act="opt", key=step_id, sub=opt["id"])))
    await pokazat_ekran(event, tekst, _kb(*ryady, _nazad("steps")))


async def ekran_kategorii(event: Sobytie, shk: Shkatulka, step_id: str, cat_id: str) -> None:
    cat = shk.kategoriya(step_id, cat_id)
    ryady = [("✏️ Название категории", Pravka(act="edit", key="cat_label", sub=f"{step_id}|{cat_id}"))]
    ryady += [(f"🔘 {o['label']}", Pravka(act="opt", key=step_id, sub=f"{cat_id}/{o['id']}")) for o in cat["options"]]
    await pokazat_ekran(event, f"📂 <b>{html.escape(cat['label'])}</b>\n\nВыберите вариант:",
                        _kb(*ryady, _nazad("st", step_id)))


async def ekran_opcii(event: Sobytie, shk: Shkatulka, step_id: str, sub: str) -> None:
    opt = najti_opciyu(shk, step_id, sub)
    tekst = f"🔘 <b>{html.escape(opt['label'])}</b>"
    ryady = [("✏️ Надпись на кнопке", Pravka(act="edit", key="opt_label", sub=f"{step_id}|{sub}"))]
    if opt.get("input"):
        tekst += f"\n\nПосле нажатия бот спрашивает:\n<i>{opt['input']}</i>"
        ryady.append(("✏️ Уточняющий вопрос", Pravka(act="edit", key="opt_input", sub=f"{step_id}|{sub}")))
    if "/" not in sub:
        tekst += f"\n\n💰 Добавляет к расчёту: <b>{opt.get('price', 0)} ₽</b>"
        ryady.append(("💰 Изменить цену", Pravka(act="edit", key="opt_price", sub=f"{step_id}|{sub}")))
    nazad = _nazad("cat", step_id, sub.split("/")[0]) if "/" in sub else _nazad("st", step_id)
    await pokazat_ekran(event, tekst, _kb(*ryady, nazad))


async def ekran_portfolio(event: Sobytie, shk: Shkatulka) -> None:
    ryady = [(s["label"], Pravka(act="pfs", key=s["id"])) for s in shk.dannye["portfolio"]]
    await pokazat_ekran(event, "🗂 <b>Примеры работ</b>\n\nВыберите сферу:", _kb(*ryady, _nazad()))


async def ekran_sfery(event: Sobytie, shk: Shkatulka, sphere_id: str) -> None:
    sfera = shk.sfera(sphere_id)
    stroki = []
    for i, rabota in enumerate(sfera["works"], 1):
        ssylka = html.escape(rabota.get("url") or "ссылка не указана")
        stroki.append(f"{i}. {html.escape(rabota['name'])}\n    🔗 {ssylka}")
    tekst = f"🗂 <b>{html.escape(sfera['label'])}</b>\n\n{sfera['intro']}\n\n" + ("\n".join(stroki) or "Пока пусто")
    ryady = [
        ("✏️ Вступительный текст", Pravka(act="edit", key="pf_intro", sub=sphere_id)),
        ("➕ Добавить работу", Pravka(act="edit", key="pf_add", sub=sphere_id)),
    ]
    ryady += [(f"🗑 Удалить №{i}", Pravka(act="pf_del", key=sphere_id, sub=str(i - 1)))
              for i in range(1, len(sfera["works"]) + 1)]
    await pokazat_ekran(event, tekst, _kb(*ryady, _nazad("pf")))


async def ekran_ceny(event: Sobytie, shk: Shkatulka) -> None:
    cennik = shk.dannye["estimate"]
    vklyucheno = shk.nastroyka.get("estimate_enabled", True)
    stroki = [
        "💰 <b>Ориентировочный расчёт стоимости</b>",
        "",
        "Клиент в конце анкеты «Новый сайт» видит сумму «от … ₽». Она складывается из базовой цены ветки, "
        "цен отмеченных вариантов (меняются в разделе «Вопросы») и цены за каждую выбранную страницу.",
        "",
        f"Статус: {'🟢 включён' if vklyucheno else '🔴 выключен'}",
        f"За каждую страницу: <b>{cennik.get('per_section', 0)} ₽</b>",
        "",
        "<b>Базовые цены:</b>",
    ]
    ryady = [("🔴 Выключить расчёт" if vklyucheno else "🟢 Включить расчёт", Pravka(act="price_tog"))]
    for flow, cena in cennik["base"].items():
        nazvanie = shk.nazvanie_vetki(flow)
        stroki.append(f"• {html.escape(nazvanie)}: {cena} ₽")
        ryady.append((f"✏️ {nazvanie}", Pravka(act="edit", key="price_base", sub=flow)))
    ryady.append(("✏️ Цена за страницу", Pravka(act="edit", key="price_page")))
    await pokazat_ekran(event, "\n".join(stroki), _kb(*ryady, _nazad()))


async def ekran_zayavok(event: Sobytie, kladovka: Kladovka) -> None:
    zayavki = kladovka.poslednie(10)
    if not zayavki:
        await pokazat_ekran(event, "📥 Заявок пока нет.", _kb(_nazad()))
        return
    ryady = [
        (f"#{z['id']} · {z['created'][5:]} · {z['name'] or '—'} · {STATUSY.get(z['status'], '')}",
         Pravka(act="lead", key=str(z["id"])))
        for z in zayavki
    ]
    await pokazat_ekran(event, "📥 <b>Последние 10 заявок</b>\n\nНажмите, чтобы открыть:", _kb(*ryady, _nazad()))


async def ekran_chata(event: Sobytie, shk: Shkatulka, nastroyki: Nastroyki_epta) -> None:
    chat = shk.nastroyka.get("manager_chat_id")
    if chat:
        sejchas = f"в групповой чат <code>{chat}</code>"
    else:
        sejchas = "в личные сообщения администраторам (" + ", ".join(map(str, sorted(nastroyki.admin_ids))) + ")"
    tekst = (
        "⚙️ <b>Куда приходят заявки</b>\n\n"
        f"Сейчас: {sejchas}\n\n"
        "Чтобы заявки приходили в общий чат менеджеров:\n"
        "1. Добавьте бота в группу.\n"
        "2. Напишите в группе команду /set_chat\n\n"
        "Менеджеры в группе смогут брать заявки в работу кнопкой."
    )
    ryady = [("↩️ Присылать мне в личку", Pravka(act="chat_reset"))] if chat else []
    await pokazat_ekran(event, tekst, _kb(*ryady, _nazad()))


# ---------- Вход и навигация ----------

@router.message(Command("admin"), F.chat.type == "private", Svoy_chelovek())
async def admin(message: Message, state: FSMContext, kladovka: Kladovka) -> None:
    await state.clear()
    await glavnyy_ekran(message, kladovka)


@router.message(Command("cancel"), Masterovoy.zhdu)
async def otmena(message: Message, state: FSMContext, kladovka: Kladovka) -> None:
    await state.clear()
    await message.answer("Отменено.")
    await glavnyy_ekran(message, kladovka)


@router.callback_query(Pravka.filter(), Svoy_chelovek())
async def navigaciya(cb: CallbackQuery, callback_data: Pravka, state: FSMContext, shk: Shkatulka,
                     kladovka: Kladovka, knopki: Knopki_epta, nastroyki: Nastroyki_epta) -> None:
    act, key, sub = callback_data.act, callback_data.key, callback_data.sub
    await cb.answer()

    match act:
        case "menu":
            await state.clear()
            await glavnyy_ekran(cb, kladovka)
        case "blocks":
            await ekran_blokov(cb, shk)
        case "blk":
            await ekran_bloka(cb, shk, key)
        case "buttons":
            await ekran_knopok(cb, shk)
        case "steps":
            await ekran_shagov(cb, shk)
        case "st":
            await ekran_shaga(cb, shk, key)
        case "cat":
            await ekran_kategorii(cb, shk, key, sub)
        case "opt":
            await ekran_opcii(cb, shk, key, sub)
        case "pf":
            await ekran_portfolio(cb, shk)
        case "pfs":
            await ekran_sfery(cb, shk, key)
        case "pf_del":
            raboty = shk.sfera(key)["works"]
            if sub.isdigit() and int(sub) < len(raboty):
                raboty.pop(int(sub))
                shk.sohranit()
            await ekran_sfery(cb, shk, key)
        case "price":
            await ekran_ceny(cb, shk)
        case "price_tog":
            shk.nastroyka["estimate_enabled"] = not shk.nastroyka.get("estimate_enabled", True)
            shk.sohranit()
            await ekran_ceny(cb, shk)
        case "leads":
            await ekran_zayavok(cb, kladovka)
        case "lead":
            zayavka = kladovka.odna(int(key))
            if zayavka is None:
                await ekran_zayavok(cb, kladovka)
                return
            tekst = Sdacha.narezat(zayavka["summary"] + f"\n\nСтатус: {STATUSY.get(zayavka['status'])}"
                                   + (f" ({html.escape(zayavka['taken_by'])})" if zayavka["taken_by"] else ""))
            for kusok in tekst[:-1]:
                await cb.message.answer(kusok)
            kb = InlineKeyboardBuilder()
            status_kb = knopki.lid(zayavka["id"], zayavka["status"])
            if status_kb:
                kb.attach(InlineKeyboardBuilder.from_markup(status_kb))
            kb.button(text="⬅️ К списку заявок", callback_data=Pravka(act="leads"))
            kb.adjust(1)
            await cb.message.answer(tekst[-1], reply_markup=kb.as_markup())
        case "csv":
            fayl = BufferedInputFile(kladovka.v_csv(), filename=f"zayavki_{datetime.now():%Y-%m-%d}.csv")
            await cb.message.answer_document(fayl, caption="📤 Все заявки. Файл открывается в Excel.")
        case "chat":
            await ekran_chata(cb, shk, nastroyki)
        case "chat_reset":
            shk.nastroyka["manager_chat_id"] = None
            shk.sohranit()
            await ekran_chata(cb, shk, nastroyki)
        case "edit":
            await nachat_pravku(cb, state, shk, key, sub)


# ---------- Правка: спрашиваем новое значение ----------

PODSKAZKA_TEKST = ("\n\nПришлите новый текст одним сообщением. Жирный, курсив и ссылки, сделанные в Telegram, "
                   "сохранятся.\nОтмена — /cancel")


async def nachat_pravku(cb: CallbackQuery, state: FSMContext, shk: Shkatulka, chto: str, sub: str) -> None:
    if chto == "block":
        sejchas = shk.dannye["blocks"][sub]["text"]
        zametka = ""
        if "{name}" in sejchas or "{sum}" in sejchas:
            zametka = "\n⚠️ Сохраните в тексте метку {name} или {sum} — туда бот подставит значение."
        vopros = f"✏️ <b>{html.escape(shk.dannye['blocks'][sub]['title'])}</b>{zametka}" + PODSKAZKA_TEKST
    elif chto == "button":
        vopros = f"🔘 Сейчас: «{html.escape(shk.knopka(sub))}»\n\nПришлите новую надпись.\nОтмена — /cancel"
    elif chto == "st_text":
        vopros = "❓ <b>Новый текст вопроса</b>" + PODSKAZKA_TEKST
    elif chto == "st_hint":
        vopros = "❓ <b>Новая подсказка под вопросом</b>\nЧтобы убрать подсказку — пришлите «-»." + PODSKAZKA_TEKST
    elif chto in ("opt_label", "cat_label"):
        vopros = "🔘 Пришлите новую надпись для кнопки.\nОтмена — /cancel"
    elif chto == "opt_input":
        vopros = "✏️ <b>Новый уточняющий вопрос</b>" + PODSKAZKA_TEKST
    elif chto in ("opt_price", "price_base", "price_page"):
        vopros = "💰 Пришлите сумму в рублях одним числом, например: 15000\nОтмена — /cancel"
    elif chto == "pf_intro":
        vopros = "🗂 <b>Новый вступительный текст для сферы</b>" + PODSKAZKA_TEKST
    elif chto == "pf_add":
        vopros = ("➕ Пришлите работу в формате:\n<code>Название | ссылка</code>\n\n"
                  "Например: <code>Сайт №4 – Кровля | https://krovlya.ru</code>\n"
                  "Ссылку можно не указывать.\nОтмена — /cancel")
    else:
        return
    await state.set_state(Masterovoy.zhdu)
    await state.update_data(pravka={"chto": chto, "sub": sub})
    await cb.message.answer(vopros)


# ---------- Правка: применяем присланное значение ----------

@router.message(Masterovoy.zhdu, F.chat.type == "private", ~F.text.startswith("/"), Svoy_chelovek())
async def primenit(message: Message, state: FSMContext, shk: Shkatulka, kladovka: Kladovka) -> None:
    pravka = (await state.get_data()).get("pravka") or {}
    chto, sub = pravka.get("chto"), pravka.get("sub", "")
    if not message.text:
        await message.answer("Пришлите, пожалуйста, текстом. Отмена — /cancel")
        return
    tekst_html = message.html_text.strip()
    tekst = message.text.strip()

    # Числовые поля проверяем отдельно, чтобы в цены не попал мусор
    chislo = None
    if chto in ("opt_price", "price_base", "price_page"):
        ochishcheno = tekst.replace(" ", "").replace("₽", "").replace("руб", "")
        if not ochishcheno.isdigit():
            await message.answer("Нужно число, например 15000. Попробуйте ещё раз или /cancel")
            return
        chislo = int(ochishcheno)

    if chto in ("button", "opt_label", "cat_label") and len(tekst) > 60:
        await message.answer("Слишком длинная надпись для кнопки (максимум 60 символов). Ещё раз или /cancel")
        return

    step_id, _, hvost = sub.partition("|")
    match chto:
        case "block":
            shk.dannye["blocks"][sub]["text"] = tekst_html
            sled = ("blk", sub, "")
        case "button":
            shk.dannye["buttons"][sub] = tekst
            sled = ("buttons", "", "")
        case "st_text":
            shk.shag(sub)["text"] = tekst_html
            sled = ("st", sub, "")
        case "st_hint":
            if tekst == "-":
                shk.shag(sub).pop("hint", None)
            else:
                shk.shag(sub)["hint"] = tekst_html
            sled = ("st", sub, "")
        case "opt_label":
            najti_opciyu(shk, step_id, hvost)["label"] = tekst
            sled = ("opt", step_id, hvost)
        case "opt_input":
            najti_opciyu(shk, step_id, hvost)["input"] = tekst_html
            sled = ("opt", step_id, hvost)
        case "opt_price":
            najti_opciyu(shk, step_id, hvost)["price"] = chislo
            sled = ("opt", step_id, hvost)
        case "cat_label":
            shk.kategoriya(step_id, hvost)["label"] = tekst
            sled = ("cat", step_id, hvost)
        case "price_base":
            shk.dannye["estimate"]["base"][sub] = chislo
            sled = ("price", "", "")
        case "price_page":
            shk.dannye["estimate"]["per_section"] = chislo
            sled = ("price", "", "")
        case "pf_intro":
            shk.sfera(sub)["intro"] = tekst_html
            sled = ("pfs", sub, "")
        case "pf_add":
            nazvanie, _, url = (s.strip() for s in tekst.partition("|"))
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url
            shk.sfera(sub)["works"].append({"name": nazvanie, "url": url})
            sled = ("pfs", sub, "")
        case _:
            await state.clear()
            await glavnyy_ekran(message, kladovka)
            return

    shk.sohranit()
    await state.clear()
    await message.answer("✅ Сохранено. Клиенты уже видят новую версию.",
                         reply_markup=_kb(("👀 Вернуться к разделу", Pravka(act=sled[0], key=sled[1], sub=sled[2])),
                                          ("🏠 Меню админки", Pravka(act="menu"))))


# ---------- Чат менеджеров и кнопки под заявками ----------

@router.message(Command("set_chat"), F.chat.type.in_({"group", "supergroup"}), Svoy_chelovek())
async def naznachit_chat(message: Message, shk: Shkatulka) -> None:
    shk.nastroyka["manager_chat_id"] = message.chat.id
    shk.sohranit()
    await message.answer("✅ Теперь новые заявки будут приходить в этот чат.")


@router.callback_query(Lid.filter())
async def lid(cb: CallbackQuery, callback_data: Lid, shk: Shkatulka, kladovka: Kladovka,
              knopki: Knopki_epta, nastroyki: Nastroyki_epta) -> None:
    v_chate_menedzherov = cb.message and cb.message.chat.id == shk.nastroyka.get("manager_chat_id")
    if not (v_chate_menedzherov or cb.from_user.id in nastroyki.admin_ids):
        await cb.answer("Нет доступа", show_alert=True)
        return

    kto = cb.from_user.full_name + (f" (@{cb.from_user.username})" if cb.from_user.username else "")
    if callback_data.act == "take":
        if not kladovka.vzyat_v_rabotu(callback_data.lead_id, kto):
            zayavka = kladovka.odna(callback_data.lead_id)
            await cb.answer(f"Заявку уже взял: {zayavka['taken_by'] if zayavka else '—'}", show_alert=True)
            return
        pripiska, status = f"\n\n🙋 <b>В работе:</b> {html.escape(kto)}", "work"
    else:
        kladovka.zakryt(callback_data.lead_id)
        pripiska, status = f"\n\n✅ <b>Закрыта</b> ({html.escape(cb.from_user.full_name)})", "done"

    await cb.answer("Готово")
    try:
        await cb.message.edit_text(cb.message.html_text + pripiska, disable_web_page_preview=True,
                                   reply_markup=knopki.lid(callback_data.lead_id, status))
    except TelegramBadRequest:
        await cb.message.edit_reply_markup(reply_markup=knopki.lid(callback_data.lead_id, status))
