import os
import re
import uuid
import json
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass


def resolve_url(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    r.raise_for_status()
    return r.url


def find_all_mp4_urls(html: str):
    patterns = [
        r'https://v1\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*',
        r'https://v\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*',
        r'https://i\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*',
        r'"url":"(https:[^"]+\.mp4[^"]*)"',
        r'"contentUrl":"(https:[^"]+\.mp4[^"]*)"',
    ]

    found = []
    for pat in patterns:
        matches = re.findall(pat, html)
        for m in matches:
            m = m.replace("\\u002F", "/").replace("\\/", "/")
            if m.startswith("https:") and m not in found:
                found.append(m)
    return found


def find_best_image(html: str, soup: BeautifulSoup):
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    patterns = [
        r'https://i\.pinimg\.com/originals/[^"\']+',
        r'https://i\.pinimg\.com/736x/[^"\']+',
        r'"image_url":"(https:[^"]+)"',
        r'"orig":"(https:[^"]+)"',
    ]

    for pat in patterns:
        matches = re.findall(pat, html)
        if matches:
            url = matches[0].replace("\\u002F", "/").replace("\\/", "/")
            return url

    return None


def extract_pinterest_media(url: str):
    real_url = resolve_url(url)
    r = requests.get(real_url, headers=HEADERS, timeout=25)
    r.raise_for_status()

    html = r.text
    soup = BeautifulSoup(html, "lxml")

    # 1. direct meta
    og_video = soup.find("meta", property="og:video")
    if og_video and og_video.get("content"):
        return "video", og_video["content"]

    # 2. search all mp4 urls
    mp4s = find_all_mp4_urls(html)
    if mp4s:
        # try longest url first, usually best quality
        mp4s.sort(key=len, reverse=True)
        return "video", mp4s[0]

    # 3. fallback image
    image_url = find_best_image(html, soup)
    if image_url:
        return "image", image_url

    return None, None


def download_file(url: str, ext: str):
    path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.{ext}")

    with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)

    return path


@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(
        "📌 Отправь ссылку на Pinterest.\n\n"
        "Я попробую скачать фото или видео."
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
            await wait_msg.edit_text("❌ Не удалось найти фото или видео.")
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
