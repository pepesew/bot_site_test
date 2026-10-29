import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from masterskaya.handlers import dialog, masterovoy, vhod, vitrina
from masterskaya.kladovka import Kladovka
from masterskaya.knopki import Knopki_epta
from masterskaya.nastroyki import Nastroyki_epta
from masterskaya.sdacha import Sdacha
from masterskaya.shkatulka import Shkatulka
from masterskaya.verstak import Sobytie, Verstak


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    nastroyki = Nastroyki_epta.iz_env()

    # Собираем все детали: шкатулку с контентом, кладовку заявок, клавиатуры и движок анкеты
    bot = Bot(nastroyki.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    shk = Shkatulka(nastroyki.scenario_path)
    kladovka = Kladovka(nastroyki.db_path)
    knopki = Knopki_epta(shk)
    verstak = Verstak(shk)
    sdacha = Sdacha(bot, shk, kladovka, knopki, nastroyki.admin_ids)

    # Движку нужно знать, что делать в конце анкеты и куда выходить по «Назад» с первого шага
    async def v_menu(event: Sobytie, state: FSMContext) -> None:
        await vhod.glavnoe_menu(event, state, shk, knopki)

    verstak.na_finish = sdacha
    verstak.v_menu = v_menu

    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data.update(
        nastroyki=nastroyki, shk=shk, kladovka=kladovka, knopki=knopki, verstak=verstak, sdacha=sdacha,
    )

    # Порядок важен: админка и ввод текста раньше, общий «перехватчик» меню — последним
    dp.include_routers(masterovoy.router, dialog.router, vitrina.router, vhod.router)

    await bot.set_my_commands(
        [BotCommand(command="start", description="Начать заново"),
         BotCommand(command="menu", description="Главное меню")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
