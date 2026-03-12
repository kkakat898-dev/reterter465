import asyncio
import logging
import os
import shutil
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from PIL import Image, ImageDraw
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- Настройки бота ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ДЛЯ_ТЕСТОВ")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Папки для временных файлов
TEMP_DIR = "temp_render"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Машина состояний (FSM) ---
class UserConfig(StatesGroup):
    waiting_for_hex_color = State()

# --- База данных (в памяти) ---
user_data = {}

def get_default_config():
    return {
        "bg_color": "#000000",
        "resolution": (1920, 530), # (ширина, высота)
        "fps": 30,
        "format": "GIF" # Или "MP4"
    }

# --- Клавиатуры ---
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Кошелёк · 10₽", callback_data="wallet")],
        [
            InlineKeyboardButton(text="🎨 Цвет фона", callback_data="set_bg_color"),
            InlineKeyboardButton(text="🔳 Разрешение", callback_data="set_resolution")
        ],
        [
            InlineKeyboardButton(text="🎞 Формат", callback_data="set_format"),
            InlineKeyboardButton(text="📂 Своя медиа", callback_data="set_media")
        ],
        [
            InlineKeyboardButton(text="😀 ЦветEmoji", callback_data="set_emoji_color"),
            InlineKeyboardButton(text="📝 Заметки", callback_data="set_notes")
        ],
        [
            InlineKeyboardButton(text="💧 Вотермарка", callback_data="set_watermark"),
            InlineKeyboardButton(text="👁 Предосмотр", callback_data="preview")
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
    res_str = f"{config['resolution'][0]}x{config['resolution'][1]}"
    
    text = (
        "😈 **Создан для пиздатого оформления ботов or сайтов**\n\n"
        "📤 **Отправь мне:**\n"
        "<code>прем эмодзи - можно несколько or стикер, ссылку на пак emoji or sticker</code>\n\n"
        "⌘ **Конфигурация:**\n"
        f"🎨 Цвет фона: <code>{config['bg_color']}</code>\n"
        f"🔳 Разрешение: <code>{res_str} {config['fps']} FPS</code>\n"
        f"🎞 Формат: <code>{config['format']}</code>"
    )
    
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# --- Хэндлеры кнопок меню ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "set_bg_color")
async def set_bg_color(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "🎨 **Введи новый HEX-цвет для фона типо:**\n\n"
        "<code>FFFFFF</code> - белый\n"
        "<code>000000</code> - черный"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Подобрать цвет", url="https://htmlcolorcodes.com/")],
        [InlineKeyboardButton(text="◁ Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(UserConfig.waiting_for_hex_color)
    await callback.answer()

# --- Хэндлеры ввода текста (Состояния) ---
@dp.message(UserConfig.waiting_for_hex_color)
async def process_hex_color(message: types.Message, state: FSMContext):
    new_color = message.text.strip().upper()
    if not new_color.startswith("#"):
        new_color = f"#{new_color}"
    
    # Простая проверка на валидность HEX
    if len(new_color) != 7 or not all(c in "#0123456789ABCDEF" for c in new_color):
        await message.answer("❌ Ошибка! Неверный формат HEX-цвета. Попробуй еще раз (например, <code>FF5733</code>).", parse_mode="HTML")
        return

    user_id = message.from_user.id
    if user_id not in user_data: user_data[user_id] = get_default_config()
    user_data[user_id]["bg_color"] = new_color
    
    await state.clear()
    await message.answer(f"✅ Цвет фона успешно изменен на <code>{new_color}</code>!", parse_mode="HTML")
    await cmd_start(message)

# --- Логика рендеринга ---

def render_banner(input_file_path, output_file_path, config):
    try:
        # Убираем '#' из цвета для moviepy
        bg_color_hex = config['bg_color'].lstrip('#')
        width, height = config['resolution']
        fps = config['fps']

        # Создаем фоновый клип
        bg_clip = ColorClip(size=(width, height), color=tuple(int(bg_color_hex[i:i+2], 16) for i in (0, 2, 4)))
        
        # Загружаем клип со стикером/эмодзи
        sticker_clip = VideoFileClip(input_file_path, has_mask=True)
        
        # Масштабируем стикер, чтобы он вписывался по высоте с небольшим отступом
        sticker_h = int(height * 0.8)
        sticker_clip = sticker_clip.resize(height=sticker_h)
        
        # Центрируем стикер на фоне
        sticker_clip = sticker_clip.set_position(("center", "center"))
        
        # Устанавливаем длительность фона равной длительности стикера
        bg_clip = bg_clip.set_duration(sticker_clip.duration)
        
        # Накладываем стикер на фон
        final_clip = CompositeVideoClip([bg_clip, sticker_clip])
        
        # Рендерим
        if config['format'] == "GIF":
            final_clip.write_gif(output_file_path, fps=fps, logger=None)
        else: # MP4
            final_clip.write_videofile(output_file_path, fps=fps, codec='libx264', audio=False, logger=None)
            
        # Закрываем клипы, чтобы освободить ресурсы
        sticker_clip.close()
        bg_clip.close()
        final_clip.close()
        
        return True
    except Exception as e:
        logging.error(f"Ошибка рендеринга: {e}")
        return False

# --- Обработка отправки стикеров/эмодзи ---
@dp.message(F.sticker | F.video_note | F.animation)
async def handle_media_for_render(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = get_default_config()
    config = user_data[user_id]
    
    status_msg = await message.answer("🔄 **Принято! Начинаю рендер с твоими настройками...**\nЭтого может занять некоторое время.", parse_mode="Markdown")
    
    # Определяем file_id в зависимости от типа медиа
    file_id = None
    file_ext = ""
    if message.sticker:
        if message.sticker.is_animated: # TGS
             await status_msg.edit_text("⚠️ К сожалению, прямая конвертация .tgs (анимированных стикеров) пока не поддерживается в этом примере. Отправь видео-стикер (.webm) или гифку.")
             return
        elif message.sticker.is_video: # WebM
            file_id = message.sticker.file_id
            file_ext = ".webm"
        else: # Обычный статический стикер
            file_id = message.sticker.file_id
            file_ext = ".webp"
    elif message.video_note:
        file_id = message.video_note.file_id
        file_ext = ".mp4"
    elif message.animation:
        file_id = message.animation.file_id
        file_ext = ".mp4" # Телеграм часто конвертирует гифки в mp4

    if not file_id:
        await status_msg.edit_text("❌ Не удалось получить файл для обработки.")
        return

    # Создаем уникальные имена для файлов
    input_path = os.path.join(TEMP_DIR, f"input_{user_id}_{file_id}{file_ext}")
    output_ext = ".gif" if config['format'] == "GIF" else ".mp4"
    output_path = os.path.join(TEMP_DIR, f"output_{user_id}_{file_id}{output_ext}")

    try:
        # Скачиваем файл
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, input_path)
        
        # Запускаем рендер в отдельном потоке, чтобы не блокировать бота
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, render_banner, input_path, output_path, config)
        
        if success:
            await status_msg.edit_text("✅ **Рендер завершен! Отправляю готовый баннер...**", parse_mode="Markdown")
            # Отправляем файл
            if config['format'] == "GIF":
                await message.answer_animation(animation=types.FSInputFile(output_path))
            else:
                await message.answer_video(video=types.FSInputFile(output_path))
        else:
            await status_msg.edit_text("❌ Произошла ошибка при рендеринге баннера.")
            
    except Exception as e:
        logging.error(f"Ошибка при обработке: {e}")
        await status_msg.edit_text(f"❌ Произошла непредвиденная ошибка.")
    finally:
        # Удаляем временные файлы
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)


# --- Запуск бота ---
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
