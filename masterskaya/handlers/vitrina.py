import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from masterskaya.knopki import Knopki_epta, Vitrina_epta
from masterskaya.sdacha import Sdacha
from masterskaya.shkatulka import Shkatulka
from masterskaya.verstak import pokazat_ekran

router = Router(name="vitrina")


class Vitrina_sost(StatesGroup):
    pishet = State()


# Карточка сферы: вступление, список работ (со ссылками, если они заданы) и подпись
def kartochka_sfery(shk: Shkatulka, sfera: dict) -> str:
    stroki = []
    for rabota in sfera["works"]:
        nazvanie = html.escape(rabota["name"])
        if rabota.get("url"):
            stroki.append(f"• <a href=\"{html.escape(rabota['url'], quote=True)}\">{nazvanie}</a>")
        else:
            stroki.append(f"• {nazvanie}")
    spisok = "\n".join(stroki) or "<i>Скоро добавим примеры 🙂</i>"
    return f"{sfera['intro']}\n\n{spisok}\n\n{shk.blok('portfolio_tail')}"


@router.callback_query(Vitrina_epta.filter())
async def sfera(cb: CallbackQuery, callback_data: Vitrina_epta, state: FSMContext,
                shk: Shkatulka, knopki: Knopki_epta) -> None:
    await cb.answer()
    if callback_data.sphere == "_other":
        await state.set_state(Vitrina_sost.pishet)
        await pokazat_ekran(cb, shk.blok("portfolio_other_ask"), knopki.pod_primerami())
        return
    najdeno = shk.sfera(callback_data.sphere)
    if najdeno is None:
        await pokazat_ekran(cb, shk.blok("portfolio_ask"), knopki.sfery())
        return
    await pokazat_ekran(cb, kartochka_sfery(shk, najdeno), knopki.pod_primerami())


# «Иное» в примерах работ: пересылаем запрос менеджеру, чтобы он подобрал примеры вручную
@router.message(Vitrina_sost.pishet, F.chat.type == "private", ~F.text.startswith("/"))
async def inoe(message: Message, state: FSMContext, shk: Shkatulka, knopki: Knopki_epta, sdacha: Sdacha) -> None:
    if not message.text:
        await message.answer(shk.blok("portfolio_other_ask"), reply_markup=knopki.pod_primerami())
        return
    user = message.from_user
    tg = f"@{html.escape(user.username)}" if user.username else html.escape(user.full_name)
    await sdacha.otpravit_menedzheru(
        "🗂 <b>Запрос примеров работ</b>\n"
        f"👤 <a href=\"tg://user?id={user.id}\">{tg}</a>\n\n"
        f"«{html.escape(message.text[:1000])}»"
    )
    await state.clear()
    await message.answer(shk.blok("portfolio_other_done"), reply_markup=knopki.pod_primerami())
