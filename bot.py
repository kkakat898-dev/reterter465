import os
import re
import uuid
import asyncio
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass


def extract_pinterest_media(url: str):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    # 1. video via og:video
    og_video = soup.find("meta", property="og:video")
    if og_video and og_video.get("content"):
        return "video", og_video["content"]

    # 2. image via og:image
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return "image", og_image["content"]

    # fallback search in html
    html = r.text

    video_match = re.search(r'https://v1\.pinimg\.com/videos/[^"\']+', html)
    if video_match:
        return "video", video_match.group(0)

    image_match = re.search(r'https://i\.pinimg\.com/originals/[^"\']+', html)
    if image_match:
        return "image", image_match.group(0)

    image_match2 = re.search(r'https://i\.pinimg\.com/736x/[^"\']+', html)
    if image_match2:
        return "image", image_match2.group(0)

    return None, None


def download_file(url: str, ext: str):
    file_id = uuid.uuid4().hex
    path = os.path.join(TEMP_DIR, f"{file_id}.{ext}")

    with requests.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    return path


@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(
        "📌 Отправь ссылку на Pinterest post/pin.\n\n"
        "Я попробую скачать фото или видео и отправить обратно."
    )


@dp.message(F.text)
async def handle_link(message: Message):
    text = message.text.strip()

    if "pinterest." not in text and "pin.it" not in text:
        await message.answer("❌ Это не похоже на ссылку Pinterest.")
        return

    wait_msg = await message.answer("⏳ Ищу медиа...")

    try:
        media_type, media_url = extract_pinterest_media(text)

        if not media_url:
            await wait_msg.edit_text("❌ Не удалось найти фото или видео по этой ссылке.")
            return

        if media_type == "video":
            path = download_file(media_url, "mp4")
            await message.answer_video(
                FSInputFile(path),
                caption="✅ Видео с Pinterest"
            )
            cleanup_file(path)
        else:
            path = download_file(media_url, "jpg")
            await message.answer_photo(
                FSInputFile(path),
                caption="✅ Фото с Pinterest"
            )
            cleanup_file(path)

        await wait_msg.delete()

    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)}")


async def main():
    print("Pinterest bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
