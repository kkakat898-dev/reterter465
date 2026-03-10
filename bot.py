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
PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(level=logging.INFO)
router = Router()

# Словари данных
PREFIXES = ["The", "Mr", "Lord", "Darth", "Sir", "Master", "Agent", "Dr", "Real", "Pro", "Cyber", "Void"]
MIDDLES = ["Yonu", "Dark", "Neon", "Quantum", "Shadow", "Iron", "Astro", "Mystic", "Crimson", "Frost"]
SUFFIXES = ["Sage", "Knight", "Ninja", "Wizard", "Hacker", "Phantom", "Dragon", "Wolf", "Samurai", "Zero"]

LEET_MAP = {'a': '4', 'e': '3', 'i': '1', 'o': '0', 's': '5', 't': '7'}

# --- Логика генерации ---

def apply_style(text: str) -> str:
    """Добавляет стиль: Leet Speak или случайные цифры в конец"""
    chance = random.random()
    if chance < 0.3: # 30% шанс на Leet Speak
        res = "".join(LEET_MAP.get(c.lower(), c) if random.random() > 0.5 else c for c in text)
        return res
    elif chance < 0.6: # 30% шанс добавить цифры в стиле '99' или '2024'
        return f"{text}_{random.randint(10, 999)}"
    return text

def gen_classic_nick():
    return f"{random.choice(PREFIXES)}{random.choice(MIDDLES)}{random.choice(SUFFIXES)}"

def gen_random_string(length=10):
    """Ник типа xR4_92pL"""
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

def generate_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and sum(c.isdigit() for c in pwd) >= 3):
            return pwd

# --- Хэндлеры ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    kb = ReplyKeyboardBuilder()
    kb.button(text="👤 Генератор Ников"), kb.button(text="🔑 Генератор Паролей")
    kb.button(text="🛠 Настройки")
    kb.adjust(2, 1)
    await message.answer(
        "⚡️ <b>GenMaster Bot v2.0</b>\n\nВыберите категорию на клавиатуре ниже:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )

@router.message(F.text == "👤 Генератор Ников")
async def nick_menu(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Стильный (TheYonuSage)", callback_data="nick_style")
    kb.button(text="🎲 Микс (xR4_92pL)", callback_data="nick_mix")
    kb.adjust(1)
    await message.answer("Выберите тип никнейма:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("nick_"))
async def handle_nick_gen(callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    result = apply_style(gen_classic_nick()) if mode == "style" else gen_random_string()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Еще раз", callback_data=callback.data)
    kb.button(text="⬅️ Назад", callback_data="back_to_main")
    
    await callback.message.edit_text(f"Ваш ник:\n<code>{result}</code>", reply_markup=kb.as_markup())

@router.message(F.text == "🔑 Генератор Паролей")
async def pass_gen(message: Message):
    pwd = generate_password()
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Сгенерировать новый", callback_data="pass_reg")
    await message.answer(f"Ваш надежный пароль:\n<code>{pwd}</code>\n\n<i>Нажми, чтобы скопировать</i>", reply_markup=kb.as_markup())

@router.callback_query(F.data == "pass_reg")
async def cb_pass(callback: CallbackQuery):
    pwd = generate_password()
    await callback.message.edit_text(
        f"Ваш надежный пароль:\n<code>{pwd}</code>", 
        reply_markup=callback.message.reply_markup
    )

@router.callback_query(F.data == "back_to_main")
async def back_home(callback: CallbackQuery):
    await callback.message.delete()
    await nick_menu(callback.message)

# --- Railway Server ---
async def handle(request):
    return web.Response(text="Bot is alive")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    
    await asyncio.gather(site.start(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
