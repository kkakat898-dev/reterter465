"""
Telegram бот генератор ников и паролей
Версия для Railway
"""

import asyncio
import logging
import random
import string
import os  # <-- ВАЖНО: для получения токена из переменных окружения

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ---------- НАСТРОЙКИ ----------
# Берем токен из переменных окружения (настройки Railway)
BOT_TOKEN = os.getenv("BOT_TOKEN")  # <-- ВАЖНО: не вставляй токен напрямую!

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------- ФУНКЦИИ ГЕНЕРАЦИИ ----------
def generate_nick(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    exclude_chars = 'lI1O0'
    clean_chars = ''.join(c for c in chars if c not in exclude_chars)
    return ''.join(random.choice(clean_chars) for _ in range(length))

def generate_password(length: int = 12) -> str:
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    all_symbols = lower + upper + digits + symbols
    password = [
        random.choice(lower),
        random.choice(upper),
        random.choice(digits),
        random.choice(symbols)
    ]
    password += random.choices(all_symbols, k=length - 4)
    random.shuffle(password)
    return ''.join(password)

# ---------- ИНИЦИАЛИЗАЦИЯ БОТА ----------
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        "Я бот-генератор случайных ников и паролей.\n"
        "Используй /generate или /gen для создания."
    )

@dp.message(Command("generate", "gen"))
async def cmd_generate(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Случайный ник", callback_data="gen_nick")],
        [InlineKeyboardButton(text="🔐 Случайный пароль", callback_data="gen_password")]
    ])
    await message.answer("Что будем генерировать?", reply_markup=keyboard)

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    await callback.answer()
    
    if callback.data == "gen_nick":
        nick = generate_nick()
        await callback.message.edit_text(
            f"🎭 <b>Твой случайный ник:</b>\n<code>{nick}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё ник", callback_data="gen_nick")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
            ])
        )
        
    elif callback.data == "gen_password":
        password = generate_password()
        await callback.message.edit_text(
            f"🔐 <b>Твой случайный пароль:</b>\n<code>{password}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё пароль", callback_data="gen_password")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
            ])
        )
        
    elif callback.data == "back_to_menu":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎭 Случайный ник", callback_data="gen_nick")],
            [InlineKeyboardButton(text="🔐 Случайный пароль", callback_data="gen_password")]
        ])
        await callback.message.edit_text("Что будем генерировать?", reply_markup=keyboard)

# ---------- ЗАПУСК ----------
async def main():
    if not BOT_TOKEN:
        logger.error("❌ Ошибка: Не указан BOT_TOKEN в переменных окружения!")
        return
    
    logger.info("🚀 Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")