import os
import re
import uuid
import asyncio
import subprocess
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageSequence

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

DEFAULT_SETTINGS = {
    "bg_color": "#000000",
    "media_color": "#FFFFFF",
    "size": "1920x530",
    "format": "gif",
    "watermark": "",
    "last_media_path": None,
    "last_media_type": None,   # image, gif, emoji
    "last_emoji": None,
}

user_settings: Dict[int, Dict[str, Any]] = {}


def get_user_data(user_id: int) -> Dict[str, Any]:
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]


class Form(StatesGroup):
    waiting_bg = State()
    waiting_media_color = State()
    waiting_size = State()
    waiting_watermark = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Цвет фона", callback_data="set_bg"),
            InlineKeyboardButton(text="🖌 Цвет медии", callback_data="set_media_color"),
        ],
        [
            InlineKeyboardButton(text="📐 Разрешение", callback_data="set_size"),
            InlineKeyboardButton(text="🖼 Формат", callback_data="set_format"),
        ],
        [
            InlineKeyboardButton(text="🧾 Водяной знак", callback_data="set_watermark"),
            InlineKeyboardButton(text="📤 Загрузить медиа", callback_data="upload_media"),
        ],
        [
            InlineKeyboardButton(text="😀 Отправить emoji", callback_data="send_emoji_help"),
            InlineKeyboardButton(text="👁 Превью / Рендер", callback_data="render_preview"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Показать настройки", callback_data="show_settings"),
        ]
    ])


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◁ Назад", callback_data="back_main")]
    ])


def format_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="PNG", callback_data="fmt_png"),
            InlineKeyboardButton(text="GIF", callback_data="fmt_gif"),
            InlineKeyboardButton(text="MP4", callback_data="fmt_mp4"),
        ],
        [InlineKeyboardButton(text="◁ Назад", callback_data="back_main")]
    ])


def parse_size(size_str: str):
    parts = size_str.lower().split("x")
    if len(parts) != 2:
        raise ValueError("Invalid size format")
    w = int(parts[0].strip())
    h = int(parts[1].strip())
    if w <= 0 or h <= 0:
        raise ValueError("Invalid size")
    return w, h


def hex_to_rgb(hex_color: str):
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        raise ValueError("HEX color must be 6 chars")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def safe_remove(path: Optional[str]):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def make_text_settings(user_id: int) -> str:
    data = get_user_data(user_id)
    return (
        "⚙️ <b>Текущая конфигурация</b>\n\n"
        f"🎨 Цвет фона: <code>{data['bg_color']}</code>\n"
        f"🖌 Цвет медии: <code>{data['media_color']}</code>\n"
        f"📐 Разрешение: <code>{data['size']}</code>\n"
        f"🖼 Формат: <code>{data['format'].upper()}</code>\n"
        f"🧾 Водяной знак: <code>{data['watermark'] or 'не задан'}</code>\n"
        f"📤 Медиа: <code>{'загружено' if data['last_media_path'] or data['last_emoji'] else 'не загружено'}</code>\n"
        f"😀 Emoji: <code>{data['last_emoji'] or 'не задан'}</code>"
    )


def fit_media(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    img = img.convert("RGBA")
    fitted = ImageOps.contain(img, (target_w, target_h))
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    x = (target_w - fitted.width) // 2
    y = (target_h - fitted.height) // 2
    canvas.paste(fitted, (x, y), fitted)
    return canvas


def add_watermark(frame: Image.Image, text: str) -> Image.Image:
    if not text:
        return frame
    frame = frame.copy()
    draw = ImageDraw.Draw(frame)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 14
    x = frame.width - tw - pad
    y = frame.height - th - pad
    draw.rounded_rectangle((x - 8, y - 4, x + tw + 8, y + th + 4), radius=8, fill=(0, 0, 0, 120))
    draw.text((x, y), text, fill=(255, 255, 255, 220), font=font)
    return frame


def recolor_rgba(img: Image.Image, target_hex: str) -> Image.Image:
    img = img.convert("RGBA")
    target = hex_to_rgb(target_hex)
    pixels = img.load()

    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            brightness = (r + g + b) / 3.0 / 255.0
            nr = int(target[0] * brightness)
            ng = int(target[1] * brightness)
            nb = int(target[2] * brightness)
            pixels[x, y] = (nr, ng, nb, a)

    return img


def render_emoji_image(emoji_text: str, size_str: str, bg_hex: str, media_hex: str, watermark: str) -> Image.Image:
    w, h = parse_size(size_str)
    bg_rgb = hex_to_rgb(bg_hex)
    media_rgb = hex_to_rgb(media_hex)

    canvas = Image.new("RGBA", (w, h), bg_rgb + (255,))
    draw = ImageDraw.Draw(canvas)

    # fallback font
    # For real emoji rendering system support differs by OS.
    # This MVP uses normal text rendering.
    font_size = min(w, h) // 2
    font = ImageFont.load_default()

    # try larger truetype if available
    possible_fonts = [
        "seguiemj.ttf",
        "Segoe UI Emoji.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    ]
    for fp in possible_fonts:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except Exception:
            pass

    bbox = draw.textbbox((0, 0), emoji_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (w - tw) // 2
    y = (h - th) // 2

    draw.text((x, y), emoji_text, font=font, fill=media_rgb + (255,))
    canvas = add_watermark(canvas, watermark)
    return canvas


def render_static_to_image(src_path: str, out_path: str, bg_hex: str, media_hex: str, size_str: str, watermark: str):
    w, h = parse_size(size_str)
    bg_rgb = hex_to_rgb(bg_hex)

    base = Image.new("RGBA", (w, h), bg_rgb + (255,))
    src = Image.open(src_path).convert("RGBA")
    src = recolor_rgba(src, media_hex)
    media = fit_media(src, w, h)
    base.alpha_composite(media)
    base = add_watermark(base, watermark)
    base.convert("RGB").save(out_path, "PNG")


def render_static_to_gif(src_path: str, out_path: str, bg_hex: str, media_hex: str, size_str: str, watermark: str):
    w, h = parse_size(size_str)
    bg_rgb = hex_to_rgb(bg_hex)

    src = Image.open(src_path).convert("RGBA")
    src = recolor_rgba(src, media_hex)
    media = fit_media(src, w, h)

    frames = []
    for _ in range(18):
        frame = Image.new("RGBA", (w, h), bg_rgb + (255,))
        frame.alpha_composite(media)
        frame = add_watermark(frame, watermark)
        frames.append(frame.convert("P", palette=Image.ADAPTIVE))

    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=60, loop=0, optimize=False)


def render_gif_to_gif(src_path: str, out_path: str, bg_hex: str, media_hex: str, size_str: str, watermark: str):
    w, h = parse_size(size_str)
    bg_rgb = hex_to_rgb(bg_hex)

    src = Image.open(src_path)
    frames = []
    durations = []

    for frame in ImageSequence.Iterator(src):
        fr = frame.convert("RGBA")
        fr = recolor_rgba(fr, media_hex)
        media = fit_media(fr, w, h)
        canvas = Image.new("RGBA", (w, h), bg_rgb + (255,))
        canvas.alpha_composite(media)
        canvas = add_watermark(canvas, watermark)
        frames.append(canvas.convert("P", palette=Image.ADAPTIVE))
        durations.append(frame.info.get("duration", 80))

    if not frames:
        raise RuntimeError("No frames in GIF")

    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False
    )


def png_to_mp4(png_path: str, mp4_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", png_path,
        "-t", "3",
        "-vf", "format=yuv420p",
        "-pix_fmt", "yuv420p",
        mp4_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gif_to_mp4(gif_path: str, mp4_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-i", gif_path,
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        mp4_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def download_file(bot: Bot, file_id: str, suffix: str = "") -> str:
    file = await bot.get_file(file_id)
    ext = suffix or os.path.splitext(file.file_path or "")[1] or ".bin"
    path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}{ext}")
    await bot.download_file(file.file_path, destination=path)
    return path


def looks_like_single_emoji(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if len(text) > 8:
        return False
    return True


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "✨ <b>coalsyr render bot</b>\n\n"
        "Поддержка:\n"
        "• image\n"
        "• static sticker\n"
        "• GIF\n"
        "• обычные emoji\n\n"
        "Можно менять:\n"
        "• цвет фона\n"
        "• цвет медии\n"
        "• размер\n"
        "• формат\n"
        "• watermark"
    )
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "back_main")
async def back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=main_menu(), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "show_settings")
async def show_settings(cb: CallbackQuery):
    await cb.message.edit_text(make_text_settings(cb.from_user.id), reply_markup=back_menu(), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "set_bg")
async def set_bg(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_bg)
    await cb.message.edit_text(
        "🎨 <b>Введи HEX-цвет фона</b>\n\nПримеры:\n<code>#000000</code>\n<code>#FFFFFF</code>",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.message(Form.waiting_bg)
async def process_bg(message: Message, state: FSMContext):
    color = message.text.strip()
    if not color.startswith("#"):
        color = "#" + color
    try:
        hex_to_rgb(color)
    except Exception:
        await message.answer("❌ Неверный HEX-цвет.")
        return

    get_user_data(message.from_user.id)["bg_color"] = color.upper()
    await state.clear()
    await message.answer("✅ Цвет фона обновлён.", reply_markup=main_menu())


@dp.callback_query(F.data == "set_media_color")
async def set_media_color(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_media_color)
    await cb.message.edit_text(
        "🖌 <b>Введи HEX-цвет для медии</b>\n\nПримеры:\n<code>#FFFFFF</code>\n<code>#00FF99</code>",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.message(Form.waiting_media_color)
async def process_media_color(message: Message, state: FSMContext):
    color = message.text.strip()
    if not color.startswith("#"):
        color = "#" + color
    try:
        hex_to_rgb(color)
    except Exception:
        await message.answer("❌ Неверный HEX-цвет.")
        return

    get_user_data(message.from_user.id)["media_color"] = color.upper()
    await state.clear()
    await message.answer("✅ Цвет медии обновлён.", reply_markup=main_menu())


@dp.callback_query(F.data == "set_size")
async def set_size(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_size)
    await cb.message.edit_text(
        "📐 <b>Введи разрешение</b>\n\nНапример:\n<code>1920x530</code>\n<code>1080x1080</code>",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.message(Form.waiting_size)
async def process_size(message: Message, state: FSMContext):
    try:
        w, h = parse_size(message.text.strip())
        if w > 4000 or h > 4000:
            raise ValueError
    except Exception:
        await message.answer("❌ Неверный формат размера.")
        return

    get_user_data(message.from_user.id)["size"] = f"{w}x{h}"
    await state.clear()
    await message.answer("✅ Разрешение обновлено.", reply_markup=main_menu())


@dp.callback_query(F.data == "set_format")
async def set_format(cb: CallbackQuery):
    await cb.message.edit_text("🖼 <b>Выбери формат вывода</b>", reply_markup=format_menu(), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data.in_({"fmt_png", "fmt_gif", "fmt_mp4"}))
async def set_format_value(cb: CallbackQuery):
    fmt = cb.data.split("_")[1]
    get_user_data(cb.from_user.id)["format"] = fmt
    await cb.message.edit_text(f"✅ Формат изменён на <b>{fmt.upper()}</b>", reply_markup=main_menu(), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "set_watermark")
async def set_watermark(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_watermark)
    await cb.message.edit_text(
        "🧾 <b>Введи текст watermark</b>\n\nОтправь <code>-</code>, чтобы убрать.",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.message(Form.waiting_watermark)
async def process_watermark(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        text = ""
    get_user_data(message.from_user.id)["watermark"] = text[:64]
    await state.clear()
    await message.answer("✅ Водяной знак обновлён.", reply_markup=main_menu())


@dp.callback_query(F.data == "upload_media")
async def upload_media(cb: CallbackQuery):
    await cb.message.edit_text(
        "📤 <b>Отправь image / sticker / GIF</b>",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.callback_query(F.data == "send_emoji_help")
async def send_emoji_help(cb: CallbackQuery):
    await cb.message.edit_text(
        "😀 <b>Просто отправь в чат обычный emoji</b>\n\nНапример:\n❤️\n🔥\n😎\n🎯",
        reply_markup=back_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


@dp.message(F.photo)
async def handle_photo(message: Message):
    data = get_user_data(message.from_user.id)
    safe_remove(data.get("last_media_path"))

    path = await download_file(bot, message.photo[-1].file_id, ".jpg")
    data["last_media_path"] = path
    data["last_media_type"] = "image"
    data["last_emoji"] = None
    await message.answer("✅ Фото загружено.", reply_markup=main_menu())


@dp.message(F.sticker)
async def handle_sticker(message: Message):
    sticker = message.sticker
    if sticker.is_animated or sticker.is_video:
        await message.answer("❌ Animated/video stickers пока не поддержаны.")
        return

    data = get_user_data(message.from_user.id)
    safe_remove(data.get("last_media_path"))

    path = await download_file(bot, sticker.file_id, ".webp")
    data["last_media_path"] = path
    data["last_media_type"] = "image"
    data["last_emoji"] = None
    await message.answer("✅ Sticker загружен.", reply_markup=main_menu())


@dp.message(F.animation)
async def handle_animation(message: Message):
    data = get_user_data(message.from_user.id)
    safe_remove(data.get("last_media_path"))

    path = await download_file(bot, message.animation.file_id, ".gif")
    data["last_media_path"] = path
    data["last_media_type"] = "gif"
    data["last_emoji"] = None
    await message.answer("✅ GIF загружен.", reply_markup=main_menu())


@dp.message(F.document)
async def handle_document(message: Message):
    doc = message.document
    name = (doc.file_name or "").lower()

    data = get_user_data(message.from_user.id)
    safe_remove(data.get("last_media_path"))

    if name.endswith(".gif"):
        path = await download_file(bot, doc.file_id, ".gif")
        data["last_media_path"] = path
        data["last_media_type"] = "gif"
        data["last_emoji"] = None
        await message.answer("✅ GIF загружен.", reply_markup=main_menu())
        return

    if any(name.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
        ext = os.path.splitext(name)[1] or ".png"
        path = await download_file(bot, doc.file_id, ext)
        data["last_media_path"] = path
        data["last_media_type"] = "image"
        data["last_emoji"] = None
        await message.answer("✅ Изображение загружено.", reply_markup=main_menu())
        return

    await message.answer("❌ Поддерживаются только image/gif/webp документы.")


@dp.message(F.text)
async def handle_emoji_text(message: Message):
    text = message.text.strip()
    if not looks_like_single_emoji(text):
        return

    data = get_user_data(message.from_user.id)
    safe_remove(data.get("last_media_path"))
    data["last_media_path"] = None
    data["last_media_type"] = "emoji"
    data["last_emoji"] = text
    await message.answer(f"✅ Emoji сохранён: {text}", reply_markup=main_menu())


@dp.callback_query(F.data == "render_preview")
async def render_preview(cb: CallbackQuery):
    user_id = cb.from_user.id
    data = get_user_data(user_id)

    fmt = data["format"]
    bg = data["bg_color"]
    media_color = data["media_color"]
    size_str = data["size"]
    watermark = data["watermark"]
    media_type = data["last_media_type"]

    if media_type is None:
        await cb.answer("Сначала отправь медиа или emoji.", show_alert=True)
        return

    base_name = uuid.uuid4().hex
    png_path = os.path.join(TEMP_DIR, f"{base_name}.png")
    gif_path = os.path.join(TEMP_DIR, f"{base_name}.gif")
    mp4_path = os.path.join(TEMP_DIR, f"{base_name}.mp4")

    try:
        if media_type == "emoji":
            emoji_img = render_emoji_image(data["last_emoji"], size_str, bg, media_color, watermark)

            if fmt == "png":
                emoji_img.convert("RGB").save(png_path, "PNG")
                await cb.message.answer_document(FSInputFile(png_path), caption="✅ Render complete (PNG)")
                safe_remove(png_path)

            elif fmt == "gif":
                frames = [emoji_img.convert("P", palette=Image.ADAPTIVE) for _ in range(18)]
                frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=60, loop=0, optimize=False)
                await cb.message.answer_animation(FSInputFile(gif_path), caption="✅ Render complete (GIF)")
                safe_remove(gif_path)

            elif fmt == "mp4":
                emoji_img.convert("RGB").save(png_path, "PNG")
                png_to_mp4(png_path, mp4_path)
                await cb.message.answer_video(FSInputFile(mp4_path), caption="✅ Render complete (MP4)")
                safe_remove(png_path)
                safe_remove(mp4_path)

            await cb.answer()
            return

        src = data.get("last_media_path")
        if not src or not os.path.exists(src):
            await cb.answer("Сначала загрузи медиа.", show_alert=True)
            return

        if fmt == "png":
            if media_type == "gif":
                first = Image.open(src)
                fr = next(ImageSequence.Iterator(first)).convert("RGBA")
                temp_first = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.png")
                fr.save(temp_first)
                render_static_to_image(temp_first, png_path, bg, media_color, size_str, watermark)
                safe_remove(temp_first)
            else:
                render_static_to_image(src, png_path, bg, media_color, size_str, watermark)

            await cb.message.answer_document(FSInputFile(png_path), caption="✅ Render complete (PNG)")
            safe_remove(png_path)

        elif fmt == "gif":
            if media_type == "gif":
                render_gif_to_gif(src, gif_path, bg, media_color, size_str, watermark)
            else:
                render_static_to_gif(src, gif_path, bg, media_color, size_str, watermark)

            await cb.message.answer_animation(FSInputFile(gif_path), caption="✅ Render complete (GIF)")
            safe_remove(gif_path)

        elif fmt == "mp4":
            if media_type == "gif":
                render_gif_to_gif(src, gif_path, bg, media_color, size_str, watermark)
                gif_to_mp4(gif_path, mp4_path)
                safe_remove(gif_path)
            else:
                render_static_to_image(src, png_path, bg, media_color, size_str, watermark)
                png_to_mp4(png_path, mp4_path)
                safe_remove(png_path)

            await cb.message.answer_video(FSInputFile(mp4_path), caption="✅ Render complete (MP4)")
            safe_remove(mp4_path)

        await cb.answer()

    except subprocess.CalledProcessError:
        await cb.message.answer("❌ Ошибка ffmpeg. Проверь, установлен ли ffmpeg.")
        await cb.answer()
    except Exception as e:
        await cb.message.answer(f"❌ Ошибка рендера: <code>{str(e)}</code>", parse_mode="HTML")
        await cb.answer()


async def main():
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
