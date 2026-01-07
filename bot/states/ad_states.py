
from aiogram.fsm.state import State, StatesGroup

class AdCreation(StatesGroup):
    region = State()
    category = State()
    ad_type = State()
    title = State()
    description = State()
    photos = State()
    video = State()
    price = State()
    phone = State()
    phone_settings = State()
    hashtags = State()
    preview = State()
    confirmation = State()
