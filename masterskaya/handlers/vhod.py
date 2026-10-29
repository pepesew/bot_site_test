from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from masterskaya.knopki import Dver, Knopki_epta
from masterskaya.shkatulka import Shkatulka
from masterskaya.verstak import Sobytie, Verstak, pokazat_ekran

router = Router(name="vhod")
router.message.filter(F.chat.type == "private")


async def glavnoe_menu(event: Sobytie, state: FSMContext, shk: Shkatulka, knopki: Knopki_epta) -> None:
    await state.clear()
    await pokazat_ekran(event, shk.blok("greeting"), knopki.glavnoe())


# /start — сначала блок конфиденциальности с кнопкой «Начать»
@router.message(CommandStart())
async def start(message: Message, state: FSMContext, shk: Shkatulka, knopki: Knopki_epta) -> None:
    await state.clear()
    await message.answer(shk.blok("privacy"), reply_markup=knopki.privacy(), disable_web_page_preview=True)


@router.message(Command("menu"))
async def menu_komanda(message: Message, state: FSMContext, shk: Shkatulka, knopki: Knopki_epta) -> None:
    await glavnoe_menu(message, state, shk, knopki)


# Подсказка для настройки: свой Telegram ID нужен, чтобы вписать себя в ADMIN_IDS
@router.message(Command("myid"))
async def moy_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


# Все переходы по меню: новый сайт, доработка, продвижение, примеры, контакты
@router.callback_query(Dver.filter())
async def dver(cb: CallbackQuery, callback_data: Dver, state: FSMContext,
               shk: Shkatulka, knopki: Knopki_epta, verstak: Verstak) -> None:
    await cb.answer()
    kuda = callback_data.kuda

    # Под финальным сообщением кнопки не стирают «спасибо», а открывают новое сообщение
    event: Sobytie = cb
    if callback_data.novoe:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        event = cb.message

    if kuda in ("new", "rework", "promo"):
        await verstak.nachat(event, state, kuda)
    elif kuda == "contacts":
        await state.clear()
        await pokazat_ekran(event, shk.blok("contacts"), knopki.kontakty())
    elif kuda == "portfolio":
        await state.clear()
        await pokazat_ekran(event, shk.blok("portfolio_ask"), knopki.sfery())
    elif kuda == "order":
        await state.clear()
        await pokazat_ekran(event, shk.blok("order_ask"), knopki.zakaz_uslugi())
    else:
        await glavnoe_menu(event, state, shk, knopki)


# Любой текст «мимо» сценария: напоминаем про кнопки или открываем меню
@router.message()
async def mimo(message: Message, state: FSMContext, verstak: Verstak) -> None:
    await verstak.napomnit(message, state)


# Старые кнопки, которые уже ничего не делают — просто гасим «часики»
@router.callback_query()
async def staraya_knopka(cb: CallbackQuery) -> None:
    await cb.answer("Эта кнопка устарела — нажмите /menu", show_alert=False)
