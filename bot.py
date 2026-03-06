"""
Telegram бот генератор ников и паролей
Версия 2.0 - Расширенные функции
Деплой на Railway
"""

import asyncio
import logging
import random
import string
import os
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ---------- НАСТРОЙКИ ----------
# Токен берется из переменных окружения Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ---------- РАСШИРЕННЫЕ ФУНКЦИИ ГЕНЕРАЦИИ ----------

def generate_nick_random(length: int = 8) -> str:
    """
    Тип 1: Рандомные буквы (верхний/нижний регистр) и цифры
    """
    chars = string.ascii_letters + string.digits
    # Убираем похожие символы для удобства
    exclude_chars = 'lI1O0'
    clean_chars = ''.join(c for c in chars if c not in exclude_chars)
    return ''.join(random.choice(clean_chars) for _ in range(length))

def generate_nick_letters(length: int = 10) -> str:
    """
    Тип 2: Только буквы (минимум 10 символов)
    """
    # Гарантируем минимум 10 символов
    if length < 10:
        length = 10
    
    # Только буквы (верхний и нижний регистр)
    chars = string.ascii_letters
    # Убираем похожие символы
    exclude_chars = 'lI'
    clean_chars = ''.join(c for c in chars if c not in exclude_chars)
    
    # Иногда делаем первую букву заглавной для красоты
    nickname = list(''.join(random.choice(clean_chars) for _ in range(length)))
    if random.choice([True, False]):
        nickname[0] = nickname[0].upper()
    
    return ''.join(nickname)

def generate_nick_style(style: str = "random") -> str:
    """
    Тип 3: Стилизованные ники
    ThegoodFAUL, xX_Dark_Xx, ProGamer и т.д.
    """
    
    # Префиксы для разных стилей
    prefixes = {
        "gamer": ["The", "Xx_", "_xX", "Pro", "Ultra", "Mega", "Super", "xX_", "_Xx"],
        "fantasy": ["Dark", "Night", "Shadow", "Moon", "Star", "Fire", "Ice", "Dragon", "Thunder"],
        "simple": ["", "Mr_", "Sir_", "Lord_", "King_", "Just_", "Not_"]
    }
    
    # Основы для разных стилей
    bases = {
        "gamer": ["Gamer", "Player", "Killer", "Hunter", "Sniper", "Warrior", "Legend", "FAUL", "Noob", "Pro"],
        "fantasy": ["Wolf", "Fang", "Blade", "Soul", "Heart", "Wing", "Claw", "Knight", "Wizard", "Druid"],
        "simple": ["John", "Mike", "Alex", "Sam", "Max", "Tom", "Leo", "Nick", "Bob", "Jim"]
    }
    
    # Суффиксы для разных стилей
    suffixes = {
        "gamer": ["", "XD", "FTW", "Pro", "GG", "99lvl", "1337", "MLG"],
        "fantasy": ["", "2000", "TheGreat", "Master", "Lord", "Jr", "Sr"],
        "simple": ["", "007", "123", "2026", "x", "yo", "bro", "man"]
    }
    
    # Выбираем случайный стиль или используем указанный
    if style == "random":
        style = random.choice(list(prefixes.keys()))
    
    # Собираем ник
    prefix = random.choice(prefixes[style])
    base = random.choice(bases[style])
    suffix = random.choice(suffixes[style])
    
    # Разные комбинации для разнообразия
    patterns = [
        f"{prefix}{base}{suffix}",
        f"{base}{suffix}",
        f"{prefix}{base}",
        f"{base}_{suffix}",
        f"{prefix}_{base}"
    ]
    
    nickname = random.choice(patterns)
    
    # Иногда делаем буквы в разном регистре для стиля
    if style == "gamer" and random.choice([True, False]):
        # Чередование регистра: xX_TeSt_Xx
        nickname = ''.join(c.upper() if i % 2 == 0 else c.lower() 
                          for i, c in enumerate(nickname))
    
    # Иногда добавляем цифры в конец
    if random.choice([True, False]) and style == "gamer":
        nickname += str(random.randint(1, 999))
    
    return nickname

def generate_password(length: int = 12) -> str:
    """
    Генерация сложного пароля
    """
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    all_symbols = lower + upper + digits + symbols
    
    # Гарантируем наличие хотя бы одного символа из каждой категории
    password = [
        random.choice(lower),
        random.choice(upper),
        random.choice(digits),
        random.choice(symbols)
    ]
    # Добавляем случайные символы до нужной длины
    password += random.choices(all_symbols, k=length - 4)
    # Перемешиваем
    random.shuffle(password)
    
    return ''.join(password)

# ---------- ИНИЦИАЛИЗАЦИЯ БОТА ----------
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ---------- ОБРАБОТЧИКИ КОМАНД ----------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветственное сообщение"""
    await message.answer(
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        "🎯 Я бот-генератор случайных ников и паролей.\n"
        "Выбирай что нужно в меню 👇",
        reply_markup=main_menu_keyboard()
    )

def main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайный ник (буквы+цифры)", callback_data="nick_random")],
        [InlineKeyboardButton(text="📝 Только буквы (10+ символов)", callback_data="nick_letters")],
        [InlineKeyboardButton(text="🎮 Стилизованный (ThegoodFAUL и др.)", callback_data="nick_style")],
        [InlineKeyboardButton(text="🔐 Случайный пароль", callback_data="password")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    return keyboard

@dp.message(Command("generate", "gen"))
async def cmd_generate(message: types.Message):
    """Главное меню генерации"""
    await message.answer(
        "🎯 <b>Выбери тип генерации:</b>",
        reply_markup=main_menu_keyboard()
    )

# Быстрые команды
@dp.message(Command("nick_random"))
async def cmd_nick_random(message: types.Message):
    """Быстрая генерация случайного ника"""
    nick = generate_nick_random(8)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_random")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    await message.answer(
        f"🎲 <b>Случайный ник:</b>\n<code>{nick}</code>",
        reply_markup=keyboard
    )

@dp.message(Command("nick_letters"))
async def cmd_nick_letters(message: types.Message):
    """Быстрая генерация ника из букв"""
    nick = generate_nick_letters(10)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_letters")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    await message.answer(
        f"📝 <b>Ник только из букв:</b>\n<code>{nick}</code>",
        reply_markup=keyboard
    )

@dp.message(Command("nick_style"))
async def cmd_nick_style(message: types.Message):
    """Быстрая генерация стилизованного ника"""
    nick = generate_nick_style("random")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_style")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    await message.answer(
        f"🎮 <b>Стилизованный ник:</b>\n<code>{nick}</code>",
        reply_markup=keyboard
    )

@dp.message(Command("password"))
async def cmd_password(message: types.Message):
    """Быстрая генерация пароля"""
    password = generate_password(12)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="password")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    await message.answer(
        f"🔐 <b>Случайный пароль:</b>\n<code>{password}</code>",
        reply_markup=keyboard
    )

# ---------- ОБРАБОТЧИК КНОПОК ----------

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    """Обрабатывает нажатия на кнопки"""
    await callback.answer()
    
    if callback.data == "nick_random":
        nick = generate_nick_random(8)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_random")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(
            f"🎲 <b>Случайный ник:</b>\n<code>{nick}</code>",
            reply_markup=keyboard
        )
        
    elif callback.data == "nick_letters":
        nick = generate_nick_letters(10)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_letters")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(
            f"📝 <b>Ник только из букв:</b>\n<code>{nick}</code>",
            reply_markup=keyboard
        )
        
    elif callback.data == "nick_style":
        nick = generate_nick_style("random")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="nick_style")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(
            f"🎮 <b>Стилизованный ник:</b>\n<code>{nick}</code>",
            reply_markup=keyboard
        )
        
    elif callback.data == "password":
        password = generate_password(12)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="password")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(
            f"🔐 <b>Случайный пароль:</b>\n<code>{password}</code>",
            reply_markup=keyboard
        )
        
    elif callback.data == "back_to_menu":
        await callback.message.edit_text(
            "🎯 <b>Выбери тип генерации:</b>",
            reply_markup=main_menu_keyboard()
        )
        
    elif callback.data == "help":
        help_text = (
            "❓ <b>Как пользоваться ботом:</b>\n\n"
            "🎲 <b>Случайный ник</b> - буквы + цифры (8 символов)\n"
            "📝 <b>Только буквы</b> - минимум 10 букв\n"
            "🎮 <b>Стилизованный</b> - ThegoodFAUL, xX_Dark_Xx и т.д.\n"
            "🔐 <b>Пароль</b> - сложный пароль 12 символов\n\n"
            "Команды:\n"
            "/gen - открыть меню\n"
            "/nick_random - быстрый ник\n"
            "/nick_letters - ник из букв\n"
            "/nick_style - стильный ник\n"
            "/password - пароль"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
        ])
        await callback.message.edit_text(help_text, reply_markup=keyboard)

# ---------- ЗАПУСК ----------
async def main():
    """Точка входа"""
    if not BOT_TOKEN:
        logger.error("❌ Ошибка: Не указан BOT_TOKEN в переменных окружения!")
        logger.error("📝 Добавь переменную BOT_TOKEN в настройках Railway")
        return
    
    logger.info("🚀 Бот запущен и готов к работе...")
    logger.info("📋 Доступные команды: /start, /gen, /nick_random, /nick_letters, /nick_style, /password")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
