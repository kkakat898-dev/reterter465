import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- Настройки бота (Токен будет браться из переменных окружения Railway) ---
import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ДЛЯ_ТЕСТОВ")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Машина состояний (FSM) для ожидания ввода пользователя ---
class UserConfig(StatesGroup):
    waiting_for_hex_color = State()
    waiting_for_resolution = State()

# --- База данных (в памяти для примера) ---
# В реальном проекте используй SQLite или PostgreSQL
user_data = {}

def get_default_config():
    return {
        "bg_color": "#000000",
        "resolution": "1920x530 60 FPS",
        "format": "GIF",
        "watermark": None
    }

# --- Клавиатуры ---
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кошелёк · 10₽", callback_data="wallet")],
        [
            InlineKeyboardButton(text="Цвет фона", callback_data="set_bg_color"),
            InlineKeyboardButton(text="Разрешение", callback_data="set_resolution")
        ],
        [
            InlineKeyboardButton(text="Формат", callback_data="set_format"),
            InlineKeyboardButton(text="Своя медиа", callback_data="set_media")
        ],
        [
            InlineKeyboardButton(text="ЦветEmoji", callback_data="set_emoji_color"),
            InlineKeyboardButton(text="Заметки", callback_data="set_notes")
        ],
        [
            InlineKeyboardButton(text="Вотермарка", callback_data="set_watermark"),
            InlineKeyboardButton(text="Предосмотр", callback_data="preview")
        ]
    ])
    return keyboard

def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◁ Назад", callback_data="back_to_main")]
    ])

# --- Хэндлеры команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = get_default_config()
    
    config = user_data[user_id]
    
    text = (
        "😈 Создан для пиздатого оформления ботов or сайтов\n\n"
        "📤 Отправь мне:\n"
        "<code>прем эмодзи - можно несколько or стикер, ссылку на пак emoji or sticker</code>\n\n"
        "⌘ Конфигурация:\n"
        f"🎨 Цвет фона: <code>{config['bg_color']}</code>\n"
        f"🔲 Разрешение: <code>{config['resolution']}</code>\n"
        f"🎞 Формат: <code>{config['format']}</code>"
    )
    
    # В идеале отправлять с картинкой: message.answer_photo(photo="URL", caption=text, ...)
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# --- Хэндлеры кнопок меню ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "set_bg_color")
async def set_bg_color(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "🎨 Введи новый HEX-цвет для фона типо:\n\n"
        "<code>FFFFFF</code> - белый\n"
        "<code>000000</code> - черный"
    )
    # Добавляем кнопку "Подобрать цвет" и "Назад"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подобрать цвет", url="https://htmlcolorcodes.com/")],
        [InlineKeyboardButton(text="◁ Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(UserConfig.waiting_for_hex_color)
    await callback.answer()

# --- Хэндлеры ввода текста (Состояния) ---
@dp.message(UserConfig.waiting_for_hex_color)
async def process_hex_color(message: types.Message, state: FSMContext):
    new_color = message.text.strip().upper()
    if not new_color.startswith("#"):
        new_color = f"#{new_color}"
    
    user_id = message.from_user.id
    user_data[user_id]["bg_color"] = new_color
    
    await state.clear()
    await message.answer(f"✅ Цвет фона успешно изменен на {new_color}!")
    await cmd_start(message) # Возвращаем в главное меню

# --- Обработка отправки стикеров/эмодзи (Скелет рендера) ---
@dp.message(F.sticker | F.animation | F.text)
async def handle_media_for_render(message: types.Message):
    # Если мы не в состоянии настройки (FSM пуст) и нам прислали стикер
    await message.answer("🔄 Принято! Начинаю рендер с твоими настройками. Это может занять несколько секунд...")
    
    # ТУТ ДОЛЖНА БЫТЬ ЛОГИКА РЕНДЕРА
    # 1. Скачиваем стикер/эмодзи
    # 2. Накладываем на фон PIL/ffmpeg
    # 3. Отправляем обратно
    
    await asyncio.sleep(2) # Имитация работы
    await message.answer("✅ Готово! (Тут будет отправляться готовая GIF/Видео)")


# --- Запуск бота ---
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
