import asyncio
import logging
import random
import string
import secrets
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080)) # Порт для Railway

logging.basicConfig(level=logging.INFO)
router = Router()

# Логика генерации
PREFIXES = ["The", "Mr", "Lord", "Darth", "Sir", "Master", "Agent", "Doctor", "Real", "Pro"]
MIDDLES = ["Yonu", "Dark", "Cyber", "Neon", "Quantum", "Shadow", "Iron", "Void", "Astro", "Mystic"]
SUFFIXES = ["Sage", "Knight", "Ninja", "Wizard", "Hacker", "Phantom", "Dragon", "Wolf", "Samurai"]

def generate_nickname():
    return f"{random.choice(PREFIXES)}{random.choice(MIDDLES)}{random.choice(SUFFIXES)}"

def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(16))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and sum(c.isdigit() for c in pwd) >= 3):
            return pwd

@router.message(CommandStart())
async def cmd_start(message: Message):
    builder = ReplyKeyboardBuilder()
    builder.button(text="👤 Никнейм"), builder.button(text="🔑 Пароль")
    builder.adjust(2)
    await message.answer("<b>Бот запущен на Railway!</b>\nВыберите действие:", reply_markup=builder.as_markup(resize_keyboard=True))

@router.message(F.text == "👤 Никнейм")
async def send_nick(message: Message):
    builder = InlineKeyboardBuilder().button(text="🔄 Еще", callback_data="gen_nick")
    await message.answer(f"Ник: <code>{generate_nickname()}</code>", reply_markup=builder.as_markup())

@router.message(F.text == "🔑 Пароль")
async def send_pass(message: Message):
    builder = InlineKeyboardBuilder().button(text="🔄 Еще", callback_data="gen_pass")
    await message.answer(f"Пароль: <code>{generate_password()}</code>", reply_markup=builder.as_markup())

@router.callback_query(F.data == "gen_nick")
async def cb_nick(callback: CallbackQuery):
    await callback.message.edit_text(f"Ник: <code>{generate_nickname()}</code>", reply_markup=callback.message.reply_markup)

@router.callback_query(F.data == "gen_pass")
async def cb_pass(callback: CallbackQuery):
    await callback.message.edit_text(f"Пароль: <code>{generate_password()}</code>", reply_markup=callback.message.reply_markup)

# Заглушка для Railway Health Check
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    # Запуск бота и легкого веб-сервера параллельно
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    
    await asyncio.gather(
        site.start(),
        dp.start_polling(bot, skip_updates=True)
    )

if __name__ == "__main__":
    asyncio.run(main())
