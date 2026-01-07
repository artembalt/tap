
from aiogram import Bot
from aiogram.types import BotCommand

async def set_bot_commands(bot: Bot):
    """Установить команды бота"""
    commands = [
        BotCommand(command="start", description="Перезапустить бота"),
        BotCommand(command="new_ad", description="Создать объявление"),
        BotCommand(command="my_ads", description="Мои объявления"),
        BotCommand(command="search", description="Поиск объявлений"),
        BotCommand(command="help", description="Справка"),
    ]
    await bot.set_my_commands(commands)
