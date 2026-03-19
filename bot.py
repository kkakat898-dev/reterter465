import asyncio
import json
import os
import tempfile
from typing import Dict, Tuple
from datetime import datetime
from pathlib import Path

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5827096612"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@StriverDev")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

# Пути
BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / "database.json"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

pending_files: Dict[str, dict] = {}

# Параметры видео - ПРЕМИУМ КАЧЕСТВО
ASPECT_RATIO = 2.35
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 816
FPS = 60

# ==================== DEBUG MODE ====================
DEBUG_FILTERS = True

# Настройки качества
VIDEO_CRF = 0
VIDEO_PRESET = "veryslow"

EMOJI_SCALE = 1.4
AUTO_SCALE = False
MAX_EMOJI_HEIGHT_PERCENT = 0.7

SATURATION = 1.4
CONTRAST = 1.2
SHARPNESS = 0.0

SCALE_ALGORITHM = "lanczos"
LANCZOS_PARAM = 5

ENABLE_DEBAND = True
ENABLE_DENOISE = True
DENOISE_STRENGTH = 1.5


class MediaUpload(StatesGroup):
    waiting_for_media = State()


async def get_video_info(file_path: str) -> dict:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            file_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        data = json.loads(stdout.decode())

        duration = None
        if 'format' in data and 'duration' in data['format']:
            duration = float(data['format']['duration'])
        elif 'streams' in data and len(data['streams']) > 0:
            stream = data['streams'][0]
            if 'duration' in stream:
                duration = float(stream['duration'])

        if duration is None:
            duration = 3.0

        info = {
            'duration': duration,
            'width': data['streams'][0].get('width', 512),
            'height': data['streams'][0].get('height', 512)
        }

        return info
    except Exception as e:
        print(f"Error getting video info: {e}")
        return {'duration': 3.0, 'width': 512, 'height': 512}


def calculate_optimal_scale(original_width: int, original_height: int) -> float:
    if not AUTO_SCALE:
        return EMOJI_SCALE

    max_height = OUTPUT_HEIGHT * MAX_EMOJI_HEIGHT_PERCENT

    if original_height <= max_height:
        return 1.0

    scale = max_height / original_height
    return scale


async def convert_webm_to_video(input_path: str, output_path: str, bg_color: str = "black") -> bool:
    import shutil

    try:
        info = await get_video_info(input_path)
        duration = info['duration']
        original_width = info['width']
        original_height = info['height']

        print(f"Original: {original_width}x{original_height}, duration: {duration}s")

        scale_factor = calculate_optimal_scale(original_width, original_height)
        print(f"Scale factor: {scale_factor}")

        frames_dir = input_path.replace(".webm", "_frames").replace(".mp4", "_frames")
        os.makedirs(frames_dir, exist_ok=True)

        extract_cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-pix_fmt", "rgba",
            "-vf", "scale=in_color_matrix=auto:out_color_matrix=auto",
            os.path.join(frames_dir, "frame_%04d.png")
        ]

        process = await asyncio.create_subprocess_exec(
            *extract_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"Extract frames error: {stderr.decode()}")
            shutil.rmtree(frames_dir, ignore_errors=True)
            return False

        frame_files = sorted([f for f in os.listdir(frames_dir) if f.endswith('.png')])
        frame_count = len(frame_files)
        if frame_count == 0:
            shutil.rmtree(frames_dir, ignore_errors=True)
            return False

        original_fps = frame_count / duration if duration > 0 else 30
        print(f"Extracted {frame_count} frames, {original_fps:.2f} fps")

        scale_flags = f"{SCALE_ALGORITHM}:param0={LANCZOS_PARAM}" if SCALE_ALGORITHM == "lanczos" else SCALE_ALGORITHM

        filters = []
        filters.append("premultiply=inplace=1")

        if scale_factor != 1.0:
            filters.append(f"scale=iw*{scale_factor}:ih*{scale_factor}:flags={scale_flags}:sws_dither=none")

        filters.append("unpremultiply=inplace=1")
        filters.append("gblur=sigma=0.3:steps=1")

        sticker_filter = ",".join(filters)

        post_filters = []

        if SHARPNESS > 0:
            sharpness_filter = f"unsharp=5:5:{SHARPNESS}:5:5:{SHARPNESS}"
            post_filters.append(sharpness_filter)
            if DEBUG_FILTERS:
                print(f"[FILTER] Sharpness: {sharpness_filter}")

        eq_params = []
        if SATURATION != 1.0:
            eq_params.append(f"saturation={SATURATION}")
        if CONTRAST != 1.0:
            eq_params.append(f"contrast={CONTRAST}")

        if eq_params:
            eq_filter = "eq=" + ":".join(eq_params)
            post_filters.append(eq_filter)
            if DEBUG_FILTERS:
                print(f"[FILTER] Color correction: {eq_filter}")

        if ENABLE_DEBAND:
            post_filters.append("gradfun=strength=3:radius=12")
            if DEBUG_FILTERS:
                print("[FILTER] Deband enabled")

        if ENABLE_DENOISE:
            post_filters.append(f"hqdn3d={DENOISE_STRENGTH}:{DENOISE_STRENGTH}:3:3")
            if DEBUG_FILTERS:
                print(f"[FILTER] Denoise: {DENOISE_STRENGTH}")

        post_filters.append("format=yuv420p")
        post_filter_str = "," + ",".join(post_filters) if post_filters else ",format=yuv420p"

        full_filter = f"[0:v]{sticker_filter}[scaled];[1:v][scaled]overlay=(W-w)/2:(H-h)/2:format=auto:shortest=1{post_filter_str}"

        if DEBUG_FILTERS:
            print(f"[FILTER] Full filter chain:")
            print(f"  Sticker: {sticker_filter}")
            print(f"  Post: {post_filter_str}")
            print(f"[OUTPUT] Force output size: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}")

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(original_fps),
            "-i", os.path.join(frames_dir, "frame_%04d.png"),
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:d={duration}:r={FPS}",
            "-filter_complex", full_filter,
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-s", f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            "-aspect", f"{ASPECT_RATIO}",
            "-r", str(FPS),
            "-t", str(duration),
            "-movflags", "+faststart",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        shutil.rmtree(frames_dir, ignore_errors=True)

        if process.returncode != 0:
            print(f"FFmpeg error: {stderr.decode()}")
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"Conversion error: {e}")
        return False


async def convert_tgs_to_video(input_path: str, output_path: str, bg_color: str = "black") -> Tuple[bool, str]:
    import gzip

    json_path = input_path.replace(".tgs", ".json")
    gif_path = input_path.replace(".tgs", ".gif")
    png_path = input_path.replace(".tgs", ".png")

    try:
        with gzip.open(input_path, 'rb') as f_in:
            with open(json_path, 'wb') as f_out:
                f_out.write(f_in.read())

        animation_created = False
        animation_path = None
        duration = 3.0
        original_width = 512
        original_height = 512

        try:
            import importlib
            rlottie = importlib.import_module("rlottie_python")
            LottieAnimation = getattr(rlottie, "LottieAnimation")

            anim = LottieAnimation.from_file(json_path)
            frame_count = anim.lottie_animation_get_totalframe()
            fps = anim.lottie_animation_get_framerate()
            duration = frame_count / fps if fps > 0 else 3.0

            width, height = anim.lottie_animation_get_size()
            original_width = width
            original_height = height

            anim.save_animation(gif_path)

            if os.path.exists(gif_path):
                animation_created = True
                animation_path = gif_path
                print(f"TGS via rlottie: {frame_count} frames, {fps} fps, {duration}s, {width}x{height}")
        except Exception as e:
            print(f"rlottie-python failed: {e}")

        if not animation_created:
            try:
                import importlib
                parsers = importlib.import_module("lottie.parsers.tgs")
                exporters = importlib.import_module("lottie.exporters.gif")

                animation = parsers.parse_tgs(input_path)
                duration = (animation.out_point - animation.in_point) / animation.frame_rate
                exporters.export_gif(animation, gif_path)

                if os.path.exists(gif_path):
                    animation_created = True
                    animation_path = gif_path
                    print("TGS via lottie library")
            except Exception as e:
                print(f"lottie library failed: {e}")

        if not animation_created:
            return False, "TGS_NO_LIBRARY"

        if animation_path:
            info = await get_video_info(animation_path)
            original_width = info.get('width', 512)
            original_height = info.get('height', 512)

        scale_factor = calculate_optimal_scale(original_width, original_height)
        print(f"Scale factor: {scale_factor}")

        scale_flags = f"{SCALE_ALGORITHM}:param0={LANCZOS_PARAM}" if SCALE_ALGORITHM == "lanczos" else SCALE_ALGORITHM

        filters = []
        filters.append("premultiply=inplace=1")

        if scale_factor != 1.0:
            filters.append(f"scale=iw*{scale_factor}:ih*{scale_factor}:flags={scale_flags}:sws_dither=none")

        filters.append("unpremultiply=inplace=1")
        filters.append("gblur=sigma=0.3:steps=1")

        sticker_filter = ",".join(filters)

        post_filters = []

        if SHARPNESS > 0:
            sharpness_filter = f"unsharp=5:5:{SHARPNESS}:5:5:{SHARPNESS}"
            post_filters.append(sharpness_filter)
            if DEBUG_FILTERS:
                print(f"[FILTER] Sharpness: {sharpness_filter}")

        eq_params = []
        if SATURATION != 1.0:
            eq_params.append(f"saturation={SATURATION}")
        if CONTRAST != 1.0:
            eq_params.append(f"contrast={CONTRAST}")

        if eq_params:
            eq_filter = "eq=" + ":".join(eq_params)
            post_filters.append(eq_filter)
            if DEBUG_FILTERS:
                print(f"[FILTER] Color correction: {eq_filter}")

        if ENABLE_DEBAND:
            post_filters.append("gradfun=strength=3:radius=12")
            if DEBUG_FILTERS:
                print("[FILTER] Deband enabled")

        if ENABLE_DENOISE:
            post_filters.append(f"hqdn3d={DENOISE_STRENGTH}:{DENOISE_STRENGTH}:3:3")
            if DEBUG_FILTERS:
                print(f"[FILTER] Denoise: {DENOISE_STRENGTH}")

        post_filters.append("format=yuv420p")
        post_filter_str = "," + ",".join(post_filters) if post_filters else ",format=yuv420p"

        full_filter = f"[1:v]{sticker_filter}[scaled];[0:v][scaled]overlay=(W-w)/2:(H-h)/2:format=auto:shortest=1{post_filter_str}"

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:d={duration}:r={FPS}",
            "-i", animation_path,
            "-filter_complex", full_filter,
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-s", f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            "-aspect", f"{ASPECT_RATIO}",
            "-r", str(FPS),
            "-t", str(duration),
            "-movflags", "+faststart",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"FFmpeg error: {stderr.decode()}")
            return False, "FFMPEG_ERROR"

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""
        return False, "FFMPEG_ERROR"

    except Exception as e:
        print(f"TGS conversion error: {e}")
        return False, str(e)
    finally:
        for path in [json_path, gif_path, png_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


async def convert_gif_to_video(input_path: str, output_path: str, bg_color: str = "black") -> bool:
    try:
        info = await get_video_info(input_path)
        duration = info['duration']
        original_width = info['width']
        original_height = info['height']

        scale_factor = calculate_optimal_scale(original_width, original_height)
        print(f"GIF: {original_width}x{original_height}, scale: {scale_factor}, duration: {duration}s")

        scale_flags = f"{SCALE_ALGORITHM}:param0={LANCZOS_PARAM}" if SCALE_ALGORITHM == "lanczos" else SCALE_ALGORITHM

        filters = []
        filters.append("premultiply=inplace=1")

        if scale_factor != 1.0:
            filters.append(f"scale=iw*{scale_factor}:ih*{scale_factor}:flags={scale_flags}:sws_dither=none")

        filters.append("unpremultiply=inplace=1")
        filters.append("gblur=sigma=0.3:steps=1")

        sticker_filter = ",".join(filters)

        post_filters = []

        if SHARPNESS > 0:
            sharpness_filter = f"unsharp=5:5:{SHARPNESS}:5:5:{SHARPNESS}"
            post_filters.append(sharpness_filter)

        eq_params = []
        if SATURATION != 1.0:
            eq_params.append(f"saturation={SATURATION}")
        if CONTRAST != 1.0:
            eq_params.append(f"contrast={CONTRAST}")

        if eq_params:
            eq_filter = "eq=" + ":".join(eq_params)
            post_filters.append(eq_filter)

        if ENABLE_DEBAND:
            post_filters.append("gradfun=strength=3:radius=12")

        if ENABLE_DENOISE:
            post_filters.append(f"hqdn3d={DENOISE_STRENGTH}:{DENOISE_STRENGTH}:3:3")

        post_filters.append("format=yuv420p")
        post_filter_str = "," + ",".join(post_filters) if post_filters else ",format=yuv420p"

        full_filter = f"[1:v]{sticker_filter}[scaled];[0:v][scaled]overlay=(W-w)/2:(H-h)/2:format=auto:shortest=1{post_filter_str}"

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:d={duration}:r={FPS}",
            "-i", input_path,
            "-filter_complex", full_filter,
            "-c:v", "libx264",
            "-preset", VIDEO_PRESET,
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-s", f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            "-aspect", f"{ASPECT_RATIO}",
            "-r", str(FPS),
            "-t", str(duration),
            "-movflags", "+faststart",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"GIF ffmpeg error: {stderr.decode()}")

        return process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"GIF conversion error: {e}")
        return False


TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ==================== БАЗА ДАННЫХ ====================
def load_db() -> dict:
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "conversions": [], "stats": {"total": 0}}


def save_db(db: dict) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_media_db() -> dict:
    db = load_db()
    if "media" not in db:
        db["media"] = {"greeting": None, "subscription": None}
        save_db(db)
    return db["media"]


def save_media(section: str, media_data: dict) -> None:
    db = load_db()
    if "media" not in db:
        db["media"] = {}
    db["media"][section] = media_data
    save_db(db)


def get_media(section: str) -> dict:
    media_db = get_media_db()
    return media_db.get(section)


def add_user(user_id: int, username: str = None, first_name: str = None) -> None:
    db = load_db()
    user_key = str(user_id)

    if user_key not in db["users"]:
        db["users"][user_key] = {
            "username": username,
            "first_name": first_name,
            "first_use": datetime.now().isoformat(),
            "conversions": 0,
            "blocked": False
        }
    else:
        db["users"][user_key]["username"] = username
        db["users"][user_key]["first_name"] = first_name

    save_db(db)


def is_user_blocked(user_id: int) -> bool:
    db = load_db()
    user_data = db["users"].get(str(user_id))
    if user_data:
        return user_data.get("blocked", False)
    return False


def toggle_user_block(user_id: int) -> bool:
    db = load_db()
    if str(user_id) in db["users"]:
        current_status = db["users"][str(user_id)].get("blocked", False)
        db["users"][str(user_id)]["blocked"] = not current_status
        save_db(db)
        return not current_status
    return False


def log_conversion(user_id: int, sticker_id: str) -> None:
    db = load_db()
    db["conversions"].append({
        "user_id": user_id,
        "sticker_id": sticker_id,
        "timestamp": datetime.now().isoformat()
    })
    db["stats"]["total"] += 1
    if str(user_id) in db["users"]:
        db["users"][str(user_id)]["conversions"] += 1
    save_db(db)


def get_format_keyboard(file_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎞 GIF", callback_data=f"format:gif:{file_id}"),
            InlineKeyboardButton(text="🎬 Видео", callback_data=f"format:video:{file_id}")
        ]
    ])


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Медиа", callback_data="admin:media")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")]
    ])


def get_media_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👋 Приветствие", callback_data="media:greeting")],
        [InlineKeyboardButton(text="📂 Подписка", callback_data="media:subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")]
    ])


def get_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Юзеры", callback_data="stats:users")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")]
    ])


def get_back_keyboard(callback_data: str = "admin:media_back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])


def get_users_list_keyboard(users: dict, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("conversions", 0),
        reverse=True
    )

    start = page * per_page
    end = start + per_page
    page_users = sorted_users[start:end]
    total_pages = (len(sorted_users) + per_page - 1) // per_page

    buttons = []
    for user_id, user_data in page_users:
        display_name = user_data.get("first_name") or user_data.get("username") or "Без имени"
        conversions = user_data.get("conversions", 0)

        buttons.append([InlineKeyboardButton(
            text=f"👤 {display_name} - {conversions}",
            callback_data=f"user:info:{user_id}"
        )])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⭠ Назад", callback_data=f"users:page:{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ⭢", callback_data=f"users:page:{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:stats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_info_keyboard(user_id: int) -> InlineKeyboardMarkup:
    db = load_db()
    user_data = db["users"].get(str(user_id))
    is_blocked = user_data.get("blocked", False) if user_data else False

    block_text = "🟢 Разблокировать" if is_blocked else "🚫 Заблокировать"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=block_text, callback_data=f"user:toggle_block:{user_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="stats:users_back")]
    ])


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подписаться", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton(text="♻️ Продолжить", callback_data="check_subscription")]
    ])


bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Subscription check error: {e}")
        return False


async def send_subscription_message(message: types.Message):
    media = get_media("subscription")
    text = "<blockquote>📂 <b>Подпишись на канал владельца чтобы продолжить</b></blockquote>"

    if media:
        media_type = media.get("type")
        file_id = media.get("file_id")

        try:
            if media_type == "photo":
                await message.answer_photo(
                    photo=file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_subscription_keyboard()
                )
            elif media_type == "video":
                await message.answer_video(
                    video=file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_subscription_keyboard()
                )
            elif media_type == "animation":
                await message.answer_animation(
                    animation=file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_subscription_keyboard()
                )
        except Exception as e:
            print(f"Subscription media error: {e}")
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_subscription_keyboard())
            save_media("subscription", None)
    else:
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_subscription_keyboard())


async def check_and_notify_subscription(message: types.Message) -> bool:
    if message.from_user.id == ADMIN_ID:
        return True

    if is_user_blocked(message.from_user.id):
        return False

    is_subscribed = await check_subscription(message.from_user.id)

    if not is_subscribed:
        await send_subscription_message(message)
        return False

    return True


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if is_user_blocked(message.from_user.id):
        return

    if message.from_user.id != ADMIN_ID:
        is_subscribed = await check_subscription(message.from_user.id)
        if not is_subscribed:
            await send_subscription_message(message)
            return

    media = get_media("greeting")
    text = "<blockquote>👾 <b>Ку, кинь мне стикер или анимированый эмодзи</b></blockquote>"

    if media:
        media_type = media.get("type")
        file_id = media.get("file_id")

        try:
            if media_type == "photo":
                await message.answer_photo(photo=file_id, caption=text, parse_mode=ParseMode.HTML)
            elif media_type == "video":
                await message.answer_video(video=file_id, caption=text, parse_mode=ParseMode.HTML)
            elif media_type == "animation":
                await message.answer_animation(animation=file_id, caption=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Media error: {e}")
            await message.answer(text, parse_mode=ParseMode.HTML)
            save_media("greeting", None)
    else:
        await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "<blockquote>⚙️ <b>Админ панель</b></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_keyboard()
    )


@dp.message(F.sticker)
async def handle_sticker(message: types.Message):
    if not await check_and_notify_subscription(message):
        return

    sticker = message.sticker

    if not sticker.is_animated and not sticker.is_video:
        await message.answer(
            "❌ <b>Это не анимированный стикер!</b>\n"
            "Отправьте анимированный стикер или видео-стикер.",
            parse_mode=ParseMode.HTML
        )
        return

    processing_msg = await message.answer(
        "<blockquote>⏳ <b>Загружаю стикер...</b></blockquote>",
        parse_mode=ParseMode.HTML
    )

    try:
        ext = ".webm" if sticker.is_video else ".tgs"
        input_path = str(TEMP_DIR / f"{sticker.file_unique_id}{ext}")
        output_path = str(OUTPUT_DIR / f"{sticker.file_unique_id}_premium.mp4")

        file = await bot.get_file(sticker.file_id)
        await bot.download_file(file.file_path, input_path)

        await processing_msg.edit_text(
            "<blockquote>⏳ <b>Конвертирую...</b></blockquote>",
            parse_mode=ParseMode.HTML
        )

        if sticker.is_video:
            success = await convert_webm_to_video(input_path, output_path)
            error_msg = ""
        else:
            success, error_msg = await convert_tgs_to_video(input_path, output_path)

        if success and os.path.exists(output_path):
            file_id = sticker.file_unique_id
            pending_files[file_id] = {
                "path": output_path,
                "input_path": input_path,
                "user_id": message.from_user.id
            }

            await processing_msg.edit_text(
                "<blockquote>⚙️ <b>Выберите формат:</b></blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_format_keyboard(file_id)
            )

            log_conversion(message.from_user.id, sticker.file_unique_id)
        else:
            if error_msg == "TGS_NO_LIBRARY":
                await processing_msg.edit_text(
                    "❌ <b>Требуется библиотека:</b>\n\n"
                    "<code>pip install rlottie-python</code>\n\n"
                    "Или используйте WEBM стикеры",
                    parse_mode=ParseMode.HTML
                )
            else:
                await processing_msg.edit_text(
                    "❌ <b>Ошибка конвертации</b>",
                    parse_mode=ParseMode.HTML
                )

            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

    except Exception as e:
        await processing_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )


@dp.message(F.animation)
async def handle_animation(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == MediaUpload.waiting_for_media and message.from_user.id == ADMIN_ID:
        await process_media_upload(message, state)
        return

    if not await check_and_notify_subscription(message):
        return

    animation = message.animation

    processing_msg = await message.answer(
        "<blockquote>⏳ <b>Загружаю GIF...</b></blockquote>",
        parse_mode=ParseMode.HTML
    )

    try:
        input_path = str(TEMP_DIR / f"{animation.file_unique_id}.mp4")
        output_path = str(OUTPUT_DIR / f"{animation.file_unique_id}_premium.mp4")

        file = await bot.get_file(animation.file_id)
        await bot.download_file(file.file_path, input_path)

        await processing_msg.edit_text(
            "<blockquote>⏳ <b>Конвертирую...</b></blockquote>",
            parse_mode=ParseMode.HTML
        )

        success = await convert_webm_to_video(input_path, output_path)

        if success and os.path.exists(output_path):
            file_id = animation.file_unique_id
            pending_files[file_id] = {
                "path": output_path,
                "input_path": input_path,
                "user_id": message.from_user.id
            }

            await processing_msg.edit_text(
                "<blockquote>⚙️ <b>Выберите формат:</b></blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_format_keyboard(file_id)
            )

            log_conversion(message.from_user.id, animation.file_unique_id)
        else:
            await processing_msg.edit_text(
                "❌ <b>Ошибка конвертации</b>",
                parse_mode=ParseMode.HTML
            )

            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

    except Exception as e:
        await processing_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )


@dp.message(F.text)
async def handle_custom_emoji(message: types.Message):
    if not message.entities:
        return

    custom_emojis = [e for e in message.entities if e.type == "custom_emoji"]

    if not custom_emojis:
        return

    if not await check_and_notify_subscription(message):
        return

    processing_msg = await message.answer(
        "<blockquote>⏳ <b>Обрабатываю эмодзи...</b></blockquote>",
        parse_mode=ParseMode.HTML
    )

    try:
        emoji_id = custom_emojis[0].custom_emoji_id
        stickers = await bot.get_custom_emoji_stickers([emoji_id])

        if not stickers:
            await processing_msg.edit_text(
                "❌ <b>Не удалось получить эмодзи</b>",
                parse_mode=ParseMode.HTML
            )
            return

        sticker = stickers[0]
        ext = ".webm" if sticker.is_video else ".tgs"
        input_path = str(TEMP_DIR / f"{emoji_id}{ext}")
        output_path = str(OUTPUT_DIR / f"{emoji_id}_premium.mp4")

        file = await bot.get_file(sticker.file_id)
        await bot.download_file(file.file_path, input_path)

        await processing_msg.edit_text(
            "<blockquote>⏳ <b>Конвертирую...</b></blockquote>",
            parse_mode=ParseMode.HTML
        )

        if sticker.is_video:
            success = await convert_webm_to_video(input_path, output_path)
            error_msg = ""
        else:
            success, error_msg = await convert_tgs_to_video(input_path, output_path)

        if success and os.path.exists(output_path):
            pending_files[emoji_id] = {
                "path": output_path,
                "input_path": input_path,
                "user_id": message.from_user.id
            }

            await processing_msg.edit_text(
                "<blockquote>⚙️ <b>Выберите формат:</b></blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_format_keyboard(emoji_id)
            )

            log_conversion(message.from_user.id, emoji_id)
        else:
            if error_msg == "TGS_NO_LIBRARY":
                await processing_msg.edit_text(
                    "❌ <b>Требуется:</b>\n"
                    "<code>pip install rlottie-python</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await processing_msg.edit_text(
                    "❌ <b>Ошибка конвертации</b>",
                    parse_mode=ParseMode.HTML
                )

            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)

    except Exception as e:
        await processing_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML
        )


@dp.callback_query(F.data.startswith("format:"))
async def handle_format_choice(callback: CallbackQuery):
    await callback.answer()
    _, format_type, file_id = callback.data.split(":")

    if file_id not in pending_files:
        await callback.message.edit_text("❌ Файл не найден")
        return

    await callback.message.edit_text(
        "<blockquote>⏳ <b>Пару секунд...</b></blockquote>",
        parse_mode=ParseMode.HTML
    )

    await handle_color_choice_direct(callback, format_type, "black", file_id)


@dp.callback_query(F.data == "check_subscription")
async def handle_check_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id

    if user_id == ADMIN_ID:
        await callback.answer("✔️ Добро пожаловать, админ!")
        await callback.message.delete()
        await cmd_start(callback.message)
        return

    is_subscribed = await check_subscription(user_id)

    if is_subscribed:
        await callback.answer("✔️ Спасибо за подписку!")
        await callback.message.delete()

        media = get_media("greeting")
        text = "<blockquote>👾 <b>Ку, кинь мне стикер или анимированый эмодзи</b></blockquote>"

        if media:
            media_type = media.get("type")
            file_id = media.get("file_id")

            try:
                if media_type == "photo":
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=text,
                        parse_mode=ParseMode.HTML
                    )
                    await bot.send_photo(chat_id=callback.message.chat.id, photo=file_id)
                elif media_type == "video":
                    await bot.send_video(
                        chat_id=callback.message.chat.id,
                        video=file_id,
                        caption=text,
                        parse_mode=ParseMode.HTML
                    )
                elif media_type == "animation":
                    await bot.send_animation(
                        chat_id=callback.message.chat.id,
                        animation=file_id,
                        caption=text,
                        parse_mode=ParseMode.HTML
                    )
            except Exception:
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
        else:
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=text,
                parse_mode=ParseMode.HTML
            )
    else:
        await callback.answer("✖️ Шо ты хитри да", show_alert=True)


async def handle_color_choice_direct(callback: CallbackQuery, format_type: str, bg_color: str, file_id: str):
    if file_id not in pending_files:
        await callback.message.edit_text("❌ Файл не найден. Отправьте эмодзи заново.")
        return

    file_data = pending_files[file_id]
    input_path = file_data.get("input_path", "")

    try:
        import time
        base_name = os.path.basename(file_data["path"]).replace("_premium.mp4", "")
        timestamp = str(int(time.time()))
        output_path = str(OUTPUT_DIR / f"{base_name}_{bg_color}_{timestamp}_premium.mp4")

        old_path = str(OUTPUT_DIR / f"{base_name}_{bg_color}_premium.mp4")
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

        if input_path.endswith(".webm") or input_path.endswith(".mp4"):
            success = await convert_webm_to_video(input_path, output_path, bg_color)
        elif input_path.endswith(".tgs"):
            success, _ = await convert_tgs_to_video(input_path, output_path, bg_color)
        else:
            success = await convert_gif_to_video(input_path, output_path, bg_color)

        if success and os.path.exists(output_path):
            video_file = FSInputFile(output_path)

            if format_type == "gif":
                await callback.message.answer_animation(video_file)
            else:
                await callback.message.answer_video(video_file)

            await callback.message.delete()

            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                if file_data.get("path") and os.path.exists(file_data["path"]):
                    os.remove(file_data["path"])
                if input_path and os.path.exists(input_path):
                    os.remove(input_path)
            except Exception:
                pass
        else:
            await callback.message.edit_text(
                "❌ <b>Ошибка конвертации</b>",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )
    finally:
        if file_id in pending_files:
            del pending_files[file_id]


@dp.callback_query(F.data.startswith("color:"))
async def handle_color_choice(callback: CallbackQuery):
    await callback.answer()
    _, format_type, bg_color, file_id = callback.data.split(":")

    if file_id not in pending_files:
        await callback.message.edit_text("❌ Файл не найден. Отправьте эмодзи заново.")
        return

    file_data = pending_files[file_id]
    input_path = file_data.get("input_path", "")

    await callback.message.edit_text(
        "<blockquote>⏳ <b>Пару секунд...</b></blockquote>",
        parse_mode=ParseMode.HTML
    )

    try:
        import time
        base_name = os.path.basename(file_data["path"]).replace("_premium.mp4", "")
        timestamp = str(int(time.time()))
        output_path = str(OUTPUT_DIR / f"{base_name}_{bg_color}_{timestamp}_premium.mp4")

        old_path = str(OUTPUT_DIR / f"{base_name}_{bg_color}_premium.mp4")
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

        if input_path.endswith(".webm") or input_path.endswith(".mp4"):
            success = await convert_webm_to_video(input_path, output_path, bg_color)
        elif input_path.endswith(".tgs"):
            success, _ = await convert_tgs_to_video(input_path, output_path, bg_color)
        else:
            success = await convert_gif_to_video(input_path, output_path, bg_color)

        if success and os.path.exists(output_path):
            video_file = FSInputFile(output_path)

            if format_type == "gif":
                await callback.message.answer_animation(video_file)
            else:
                await callback.message.answer_video(video_file)

            await callback.message.delete()

            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                if file_data.get("path") and os.path.exists(file_data["path"]):
                    os.remove(file_data["path"])
                if input_path and os.path.exists(input_path):
                    os.remove(input_path)
            except Exception:
                pass
        else:
            await callback.message.edit_text(
                "❌ <b>Ошибка конвертации</b>",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )
    finally:
        if file_id in pending_files:
            del pending_files[file_id]


@dp.callback_query(F.data.startswith("admin:"))
async def handle_admin_callbacks(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    await callback.answer()
    action = callback.data.split(":")[1]

    if action == "media":
        await callback.message.delete()
        await callback.message.answer(
            "<blockquote>🖼 <b>Управление медиа</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_media_management_keyboard()
        )

    elif action == "stats":
        db = load_db()
        total_users = len(db["users"])
        total_conversions = db["stats"]["total"]

        await callback.message.delete()
        await callback.message.answer(
            f"<blockquote>📊 <b>Статистика</b></blockquote>\n\n"
            f"👤 <b>Пользователей:</b> <code>{total_users}</code>\n"
            f"♻️ <b>Конвертаций:</b> <code>{total_conversions}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_stats_keyboard()
        )

    elif action == "back":
        await callback.message.delete()
        await callback.message.answer(
            "<blockquote>⚙️ <b>Админ панель</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )

    elif action == "media_back":
        await callback.message.delete()
        await callback.message.answer(
            "<blockquote>🖼 <b>Управление медиа</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_media_management_keyboard()
        )


@dp.callback_query(F.data.startswith("media:"))
async def handle_media_callbacks(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    await callback.answer()
    section = callback.data.split(":")[1]

    await state.update_data(section=section)
    await state.set_state(MediaUpload.waiting_for_media)

    current_media = get_media(section)

    section_names = {
        "greeting": "👋 Приветствие",
        "subscription": "📂 Подписка"
    }

    section_name = section_names.get(section, section)
    text = f"<blockquote>🖼 <b>Отправьте фото, видео или GIF для раздела:</b> {section_name}</blockquote>"

    if current_media:
        media_type = current_media.get("type")
        file_id = current_media.get("file_id")

        if media_type == "photo":
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=file_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard("admin:media_back")
            )
        elif media_type == "video":
            await callback.message.delete()
            await callback.message.answer_video(
                video=file_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard("admin:media_back")
            )
        elif media_type == "animation":
            await callback.message.delete()
            await callback.message.answer_animation(
                animation=file_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_back_keyboard("admin:media_back")
            )
    else:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard("admin:media_back")
        )


@dp.callback_query(F.data.startswith("stats:"))
async def handle_stats_callbacks(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    await callback.answer()
    action = callback.data.split(":")[1]

    if action == "users":
        db = load_db()
        users = db["users"]

        await callback.message.delete()
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text="<blockquote>📄 <b>Список всех юзеров бота</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_users_list_keyboard(users)
        )

    elif action == "users_back":
        db = load_db()
        users = db["users"]

        await bot.send_message(
            chat_id=callback.message.chat.id,
            text="<blockquote>📄 <b>Список всех юзеров бота</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_users_list_keyboard(users)
        )

        await callback.message.delete()


@dp.callback_query(F.data.startswith("user:info:"))
async def handle_user_info(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    await callback.answer()
    user_id = callback.data.split(":")[2]

    db = load_db()
    user_data = db["users"].get(user_id)

    if not user_data:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    display_name = user_data.get("first_name") or user_data.get("username") or "Без имени"
    username = user_data.get("username", "Без юзернейма")
    conversions = user_data.get("conversions", 0)
    is_blocked = user_data.get("blocked", False)

    status_emoji = "🚫" if is_blocked else "✔️"
    status_text = "Заблокирован" if is_blocked else "Активен"

    text = (
        f"👤 <b>Юзер:</b> {display_name}\n\n"
        f"<blockquote>🏷️ <b>Тег:</b> @{username}\n"
        f"🪪 <b>ID:</b> <code>{user_id}</code>\n"
        f"♻️ <b>Конвертаций:</b> <code>{conversions}</code>\n"
        f"{status_emoji} <b>Статус:</b> {status_text}</blockquote>"
    )

    await callback.message.delete()

    try:
        photos = await bot.get_user_profile_photos(int(user_id), limit=1)
        if photos.total_count > 0:
            photo_id = photos.photos[0][-1].file_id
            await callback.message.answer_photo(
                photo=photo_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_user_info_keyboard(int(user_id))
            )
        else:
            await callback.message.answer(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_user_info_keyboard(int(user_id))
            )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_user_info_keyboard(int(user_id))
        )


@dp.callback_query(F.data.startswith("user:toggle_block:"))
async def handle_toggle_block(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])

    new_status = toggle_user_block(user_id)

    if new_status:
        await callback.answer("🚫 Пользователь заблокирован", show_alert=True)
    else:
        await callback.answer("🟢 Пользователь разблокирован", show_alert=True)

    db = load_db()
    user_data = db["users"].get(str(user_id))

    if not user_data:
        return

    display_name = user_data.get("first_name") or user_data.get("username") or "Без имени"
    username = user_data.get("username", "Без юзернейма")
    conversions = user_data.get("conversions", 0)
    is_blocked = user_data.get("blocked", False)

    status_emoji = "🚫" if is_blocked else "✔️"
    status_text = "Заблокирован" if is_blocked else "Активен"

    text = (
        f"👤 <b>Юзер:</b> {display_name}\n\n"
        f"<blockquote>🏷️ <b>Тег:</b> @{username}\n"
        f"🪪 <b>ID:</b> <code>{user_id}</code>\n"
        f"♻️ <b>Конвертаций:</b> <code>{conversions}</code>\n"
        f"{status_emoji} <b>Статус:</b> {status_text}</blockquote>"
    )

    try:
        await callback.message.edit_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_user_info_keyboard(user_id)
        )
    except Exception:
        await callback.message.edit_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_user_info_keyboard(user_id)
        )


@dp.callback_query(F.data.startswith("users:page:"))
async def handle_users_pagination(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return

    await callback.answer()
    page = int(callback.data.split(":")[2])

    db = load_db()
    users = db["users"]

    await callback.message.edit_text(
        text="<blockquote>📄 <b>Список всех юзеров бота</b></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_users_list_keyboard(users, page=page)
    )


@dp.message(MediaUpload.waiting_for_media, F.photo | F.video | F.animation)
async def process_media_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    section = data.get("section")

    media_data = {}

    if message.photo:
        media_data = {
            "type": "photo",
            "file_id": message.photo[-1].file_id
        }
    elif message.video:
        media_data = {
            "type": "video",
            "file_id": message.video.file_id
        }
    elif message.animation:
        media_data = {
            "type": "animation",
            "file_id": message.animation.file_id
        }

    save_media(section, media_data)
    await state.clear()

    await message.answer(
        "<blockquote>✔️ <b>Медиа успешно сохранено!</b></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard("admin:media_back")
    )


async def main():
    print("✨ Premium Emoji Bot запущен!")
    print("=" * 50)
    print(f"Python env OK")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print(f"CHANNEL_ID: {CHANNEL_ID}")
    print("=" * 50)

    if not DB_FILE.exists():
        save_db({"users": {}, "conversions": [], "stats": {"total": 0}, "media": {"greeting": None, "subscription": None}})

    try:
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=ADMIN_ID))
        print("🗑️ Старые команды удалены")
    except Exception:
        pass

    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="🚀 Запустить бота")
        ],
        scope=BotCommandScopeDefault()
    )
    print("✔️ Команды для пользователей установлены")

    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="🚀 Запустить бота"),
            BotCommand(command="admin", description="⚙️ Админ панель")
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID)
    )
    print("✔️ Команды для админа установлены")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
