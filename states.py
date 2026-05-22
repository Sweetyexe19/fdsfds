from aiogram.fsm.state import State, StatesGroup


class BuyQuantity(StatesGroup):
    waiting_quantity = State()


class AdminCategory(StatesGroup):
    name = State()
    description = State()
    price = State()
    edit_field = State()
    edit_value = State()


class AdminProducts(StatesGroup):
    waiting_file = State()


class AdminSettings(StatesGroup):
    waiting_value = State()


class AdminManualSell(StatesGroup):
    waiting_product_id = State()
