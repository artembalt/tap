
from aiogram.fsm.state import State, StatesGroup

class SearchStates(StatesGroup):
    region = State()
    category = State()
    query = State()
    results = State()
