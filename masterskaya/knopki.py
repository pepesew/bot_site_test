from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from masterskaya.shkatulka import Shkatulka


# Нажатие в шагах сценария: выбрать, отметить, продолжить, назад, разделы сайта
class Tyk(CallbackData, prefix="t"):
    act: str
    step: str
    opt: str = ""
    cat: str = ""


# Переходы по разделам меню
class Dver(CallbackData, prefix="m"):
    kuda: str
    novoe: int = 0


# Выбор сферы в «Примерах наших работ»
class Vitrina_epta(CallbackData, prefix="v"):
    sphere: str


# Кнопки под заявкой в чате менеджера
class Lid(CallbackData, prefix="l"):
    act: str
    lead_id: int


# Кнопки админ-панели
class Pravka(CallbackData, prefix="a"):
    act: str
    key: str = ""
    sub: str = ""


# Набор готовых клавиатур меню, тексты кнопок берутся из шкатулки
class Knopki_epta:
    def __init__(self, shk: Shkatulka):
        self.shk = shk

    def _k(self, key: str) -> str:
        return self.shk.knopka(key)

    def privacy(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("start"), callback_data=Dver(kuda="home"))
        return kb.as_markup()

    def glavnoe(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("menu_new"), callback_data=Dver(kuda="new"))
        kb.button(text=self._k("menu_rework"), callback_data=Dver(kuda="rework"))
        kb.button(text=self._k("menu_promo"), callback_data=Dver(kuda="promo"))
        kb.button(text=self._k("menu_portfolio"), callback_data=Dver(kuda="portfolio"))
        kb.button(text=self._k("menu_contacts"), callback_data=Dver(kuda="contacts"))
        kb.adjust(1)
        return kb.as_markup()

    def kontakty(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("home"), callback_data=Dver(kuda="home"))
        kb.button(text=self._k("order_site"), callback_data=Dver(kuda="new"))
        kb.button(text=self._k("menu_promo"), callback_data=Dver(kuda="promo"))
        kb.button(text=self._k("rework_site"), callback_data=Dver(kuda="rework"))
        kb.adjust(1)
        return kb.as_markup()

    def posle_zayavki(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("home_back"), callback_data=Dver(kuda="home", novoe=1))
        kb.button(text=self._k("menu_portfolio"), callback_data=Dver(kuda="portfolio", novoe=1))
        kb.button(text=self._k("contact_direct"), callback_data=Dver(kuda="contacts", novoe=1))
        kb.adjust(1)
        return kb.as_markup()

    def sfery(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        for sfera in self.shk.dannye["portfolio"]:
            kb.button(text=sfera["label"], callback_data=Vitrina_epta(sphere=sfera["id"]))
        kb.button(text="✍️ Иное", callback_data=Vitrina_epta(sphere="_other"))
        kb.button(text=self._k("back"), callback_data=Dver(kuda="home"))
        kb.adjust(1)
        return kb.as_markup()

    def pod_primerami(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("order_service"), callback_data=Dver(kuda="order"))
        kb.button(text=self._k("back_spheres"), callback_data=Dver(kuda="portfolio"))
        kb.adjust(1)
        return kb.as_markup()

    def zakaz_uslugi(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=self._k("create_site"), callback_data=Dver(kuda="new"))
        kb.button(text=self._k("menu_rework"), callback_data=Dver(kuda="rework"))
        kb.button(text=self._k("menu_promo"), callback_data=Dver(kuda="promo"))
        kb.button(text=self._k("home"), callback_data=Dver(kuda="home"))
        kb.adjust(1)
        return kb.as_markup()

    def lid(self, lead_id: int, status: str = "new") -> InlineKeyboardMarkup | None:
        kb = InlineKeyboardBuilder()
        if status == "new":
            kb.button(text="🙋 Взять в работу", callback_data=Lid(act="take", lead_id=lead_id))
        elif status == "work":
            kb.button(text="✅ Закрыть заявку", callback_data=Lid(act="done", lead_id=lead_id))
        else:
            return None
        return kb.as_markup()
