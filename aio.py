import os
import re
import logging
import requests
from typing import Optional
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "xx"  # Replace with your actual token
DOWNLOAD_FOLDER = "downloaded_media"

# Create download folder if it doesn't exist
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(title: str) -> str:
    """Remove invalid characters from filenames"""
    return re.sub(r'[<>:"/\\|?*]', '', title)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message"""
    await update.message.reply_text(
        "🎵 Media Downloader Bot 🎵\n\n"
        "Send me:\n"
        "- TikTok URL to download videos\n"
        "- YouTube URL to convert to MP3\n\n"
        "I'll save everything to your local folder!"
    )

def download_youtube_audio(url: str) -> Optional[str]:
    """Download YouTube audio as MP3 using yt-dlp library"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'quiet': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get('title', 'audio'))
            mp3_path = os.path.join(DOWNLOAD_FOLDER, f"{title}.mp3")
            
            if os.path.exists(mp3_path):
                return mp3_path
            raise Exception("MP3 file was not created")
            
    except Exception as e:
        logger.error(f"YouTube download failed: {str(e)}")
        return None

def download_tiktok_video(url: str) -> Optional[str]:
    """Download TikTok video using tikwm.com API"""
    try:
        api_url = "https://www.tikwm.com/api/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json",
        }
        
        params = {"url": url, "hd": "1"}
        response = requests.post(api_url, headers=headers, data=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"API error: {data.get('msg')}")
        
        video_url = data.get("data", {}).get("play")
        if not video_url:
            raise ValueError("No video URL found")
        
        video_id = url.split("/")[-1].split("?")[0]
        filename = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
        
        with requests.get(video_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            raise ValueError("Downloaded file is empty")
        
        return filename

    except Exception as e:
        logger.error(f"TikTok download error: {str(e)}")
        return None

async def process_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle YouTube URL conversion to MP3"""
    await update.message.reply_text("⏳ Converting YouTube video to MP3...")
    
    audio_path = download_youtube_audio(url)
    
    if audio_path:
        file_size = os.path.getsize(audio_path)
        context.user_data['last_download'] = audio_path
        
        keyboard = [
            [InlineKeyboardButton("Yes, send me the MP3", callback_data="send_audio")],
            [InlineKeyboardButton("No, just save it", callback_data="dont_send")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ YouTube audio converted!\n"
            f"🎵 Saved as: {os.path.basename(audio_path)}\n"
            f"📏 Size: {file_size/1024/1024:.2f} MB\n\n"
            "Send you the MP3 in Telegram?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Failed to convert YouTube video")

async def process_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Handle TikTok video download"""
    await update.message.reply_text("⏳ Downloading TikTok video...")
    
    video_path = download_tiktok_video(url)
    
    if video_path:
        file_size = os.path.getsize(video_path)
        context.user_data['last_download'] = video_path
        
        keyboard = [
            [InlineKeyboardButton("Yes, send me the video", callback_data="send_video")],
            [InlineKeyboardButton("No, just save it", callback_data="dont_send")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ TikTok video downloaded!\n"
            f"📁 Saved to: {video_path}\n"
            f"📏 Size: {file_size/1024/1024:.2f} MB\n\n"
            "Send you the video in Telegram?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Failed to download TikTok video")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route messages to appropriate handlers"""
    message = update.message.text
    
    if "tiktok.com" in message.lower():
        await process_tiktok(update, context, message)
    elif "youtube.com" in message.lower() or "youtu.be" in message.lower():
        await process_youtube(update, context, message)
    else:
        await update.message.reply_text("Please send a valid TikTok or YouTube URL")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses"""
    query = update.callback_query
    await query.answer()
    
    media_path = context.user_data.get('last_download')
    
    if not media_path or not os.path.exists(media_path):
        await query.edit_message_text("❌ Error: File not found")
        return
    
    if query.data == "send_video":
        with open(media_path, 'rb') as media_file:
            await query.message.reply_video(
                video=media_file,
                caption="Here's your TikTok video!"
            )
        await query.edit_message_text("✅ Video sent!")
    
    elif query.data == "send_audio":
        with open(media_path, 'rb') as media_file:
            await query.message.reply_audio(
                audio=media_file,
                caption="Here's your YouTube audio!"
            )
        await query.edit_message_text("✅ Audio sent!")
    
    else:
        await query.edit_message_text("✅ Saved to your downloads folder!")

def main():
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
