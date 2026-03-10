import asyncio
import logging
import random
import string
import secrets
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Railway подставит это значение из настроек проекта
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
router = Router()

# Списки для генерации ников
PREFIXES = ["The", "Mr", "Lord", "Darth", "Sir", "Master", "Agent", "Doctor", "Real", "Pro", "Captain"]
MIDDLES = ["Yonu", "Dark", "Cyber", "Neon", "Quantum", "Shadow", "Iron", "Void", "Astro", "Mystic"]
SUFFIXES = ["Sage", "Knight", "Ninja", "Wizard", "Hacker", "Phantom", "Dragon", "Wolf", "Samurai"]

def generate_nickname() -> str:
    return f"{random.choice(PREFIXES)}{random.choice(MIDDLES)}{random.choice(SUFFIXES)}"

def generate_password(length: int = 16) -> str:
    length = max(13, length)
    # Исключаем похожие символы (l, 1, O, 0) для удобства
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) 
            and sum(c.isdigit() for c in pwd) >= 3):
            return pwd

@router.message(CommandStart())
async def cmd_start(message: Message):
    builder = ReplyKeyboardBuilder()
    builder.button(text="👤 Никнейм")
    builder.button(text="🔑 Пароль")
    builder.adjust(2)
    await message.answer(
        "<b>Генератор активен!</b>\nВыберите действие ниже:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(F.text == "👤 Никнейм")
async def send_nick(message: Message):
    nick = generate_nickname()
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Еще один", callback_data="gen_nick")
    await message.answer(f"Ваш ник: <code>{nick}</code>", reply_markup=builder.as_markup())

@router.message(F.text == "🔑 Пароль")
async def send_pass(message: Message):
    pwd = generate_password()
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Другой пароль", callback_data="gen_pass")
    await message.answer(f"Надежный пароль:\n<code>{pwd}</code>", reply_markup=builder.as_markup())

@router.callback_query(F.data == "gen_nick")
async def callback_nick(callback: CallbackQuery):
    await callback.message.edit_text(
        f"Ваш ник: <code>{generate_nickname()}</code>",
        reply_markup=callback.message.reply_markup
    )
    await callback.answer()

@router.callback_query(F.data == "gen_pass")
async def callback_pass(callback: CallbackQuery):
    await callback.message.edit_text(
        f"Надежный пароль:\n<code>{generate_password()}</code>",
        reply_markup=callback.message.reply_markup
    )
    await callback.answer()

async def main():
    if not BOT_TOKEN:
        logging.error("Переменная BOT_TOKEN не найдена!")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
