from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from masterskaya.knopki import Tyk
from masterskaya.verstak import Rabota, Verstak

router = Router(name="dialog")
router.message.filter(F.chat.type == "private")


# Все кнопки внутри анкеты разбираются здесь и передаются верстаку
@router.callback_query(Tyk.filter())
async def tyk(cb: CallbackQuery, callback_data: Tyk, state: FSMContext, verstak: Verstak) -> None:
    s, o, c = callback_data.step, callback_data.opt, callback_data.cat
    match callback_data.act:
        case "pick":
            await verstak.vybor(cb, state, s, o)
        case "tog":
            await verstak.otmetka(cb, state, s, o)
        case "ok":
            await verstak.dalee(cb, state, s)
        case "back":
            await verstak.nazad(cb, state, s)
        case "cancel":
            await verstak.otmena(cb, state, s)
        case "cat":
            await verstak.kategoriya(cb, state, s, c)
        case "ctog":
            await verstak.kat_otmetka(cb, state, s, c, o)
        case "cadd":
            await verstak.kat_dobavit(cb, state, s, c)
        case "cback":
            await verstak.k_kategoriyam(cb, state, s)
        case "sother":
            await verstak.razdely_inoe(cb, state, s)
        case "sdone":
            await verstak.razdely_gotovo(cb, state, s)
        case _:
            await cb.answer()


# Ручной ввод: телефон карточкой контакта
@router.message(Rabota.pishet, F.contact)
async def kontakt(message: Message, state: FSMContext, verstak: Verstak) -> None:
    await verstak.prinyat_kontakt(message, state)


# Ручной ввод: текст, файл ТЗ или фото
@router.message(Rabota.pishet, ~F.text.startswith("/"))
async def vvod(message: Message, state: FSMContext, verstak: Verstak) -> None:
    await verstak.prinyat_vvod(message, state)
