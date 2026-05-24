import os

try:
    import telebot
    from telebot import types
except ImportError:
    raise SystemExit("Missing dependency: pyTelegramBotAPI. Install it with `pip install pyTelegramBotAPI`.")

try:
    import yt_dlp
except ImportError:
    raise SystemExit("Missing dependency: yt-dlp. Install it with `pip install yt-dlp`.")

# 1. Bot token should be provided through an environment variable for security.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN environment variable. Set it with `BOT_TOKEN=your_token_here`.")

bot = telebot.TeleBot(BOT_TOKEN)

# 2. Create a local folder to temporarily store videos
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Donation QR image path (Updated to point to the qr-code folder)
DONATION_QR_PATH = os.path.join(SCRIPT_DIR, "qr-code", "QRCode.jpg")
if not os.path.exists(DONATION_QR_PATH):
    raise SystemExit(
        f"Missing donation QR image: {DONATION_QR_PATH}. "
        "Place the file in the telegram-bot/qr-code folder."
    )

# 3. Dictionary to temporarily hold links
user_links = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 Welcome! Send me a link from **YouTube, TikTok, or Facebook**, and I will download the video for you."
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    # Basic validation to ensure the user sent a valid link
    valid_domains = ['youtube.com', 'youtu.be', 'tiktok.com', 'facebook.com', 'fb.watch']
    if not any(domain in url for domain in valid_domains):
        bot.reply_to(message, "❌ Please send a valid link from YouTube, TikTok, or Facebook.")
        return

    # Store the URL for this specific user chat ID
    user_links[message.chat.id] = url

    # Create the Inline Keyboard Buttons
    markup = types.InlineKeyboardMarkup()
    btn_download = types.InlineKeyboardButton("⬇️ Download Video", callback_data="download_video")
    btn_donate = types.InlineKeyboardButton("☕ Donation", callback_data="donation_qr")
    
    # Use .row() to put them side-by-side
    markup.row(btn_download, btn_donate)

    bot.reply_to(message, "🔗 Link detected! What would you like to do?", reply_markup=markup)

# Handle the Download button click
@bot.callback_query_handler(func=lambda call: call.data == "download_video")
def process_download(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)

    # If the bot restarted or link was lost
    if not url:
        bot.answer_callback_query(call.id, "❌ Error: Link expired. Please send the link again.", show_alert=True)
        return

    # Acknowledge the button click so it stops loading
    bot.answer_callback_query(call.id)

    # Protect against crashing if the callback is triggered from the media message
    if call.message.content_type == 'text':
        status_msg = bot.edit_message_text("⏳ Processing your video... This might take a minute.", 
                                           chat_id=chat_id, 
                                           message_id=call.message.message_id)
    else:
        status_msg = bot.send_message(chat_id, "⏳ Processing your video... This might take a minute.")

    # Configure yt-dlp options
    ydl_opts = {
        'format': 'best[ext=mp4][filesize<=50M]/best[filesize<=50M]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    filename = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract video info and download
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Locate the exact file name
            base_name = os.path.splitext(filename)[0]
            for file in os.listdir(DOWNLOAD_DIR):
                if file.startswith(os.path.basename(base_name)):
                    filename = os.path.join(DOWNLOAD_DIR, file)
                    break

        # Let the user know the download finished and upload is starting
        bot.edit_message_text("⬆️ Uploading to Telegram...", chat_id=chat_id, message_id=status_msg.message_id)
        
        # --- Final Video Output Formatting ---
        video_markup = types.InlineKeyboardMarkup()
        btn_download = types.InlineKeyboardButton("⬇️ Download Video", callback_data="download_video")
        btn_donate = types.InlineKeyboardButton("☕ Donation", callback_data="donation_qr")
        
        # .row() places the buttons exactly side-by-side below the video
        video_markup.row(btn_download, btn_donate)

        # The caption text formatted like your screenshot
        # IMPORTANT: Change @YourBotUsername to your actual bot's handle
        caption_text = "Successfully download the video\n\nPowered by @YourBotUsername"

        # Send the video file back to the chat with the caption and buttons attached
        with open(filename, 'rb') as video:
            bot.send_video(chat_id, video, caption=caption_text, reply_markup=video_markup)
            
        # Delete the temporary status message to keep the chat clean
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        error_msg = str(e)
        if "max-filesize" in error_msg or "filesize" in error_msg:
            bot.edit_message_text("❌ The video is larger than Telegram's 50MB bot limit.", chat_id=chat_id, message_id=status_msg.message_id)
        else:
            bot.edit_message_text("❌ Failed to download. The video might be private, deleted, or unsupported.", chat_id=chat_id, message_id=status_msg.message_id)
            print(f"Error details: {e}")
            
    finally:
        # Cleanup: Delete the local file so your hard drive doesn't fill up
        if filename and os.path.exists(filename):
            os.remove(filename)

# Handle the Donation button click by sending the QR code image
@bot.callback_query_handler(func=lambda call: call.data == "donation_qr")
def process_donation(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id, "📩 Sending donation QR...")
    
    if not os.path.exists(DONATION_QR_PATH):
        # Improved error message to tell you exactly where it's looking
        bot.send_message(chat_id, f"❌ Donation QR image not found at: {DONATION_QR_PATH}")
        return

    with open(DONATION_QR_PATH, 'rb') as qr_file:
        bot.send_photo(chat_id, qr_file, caption="Scan this QR code to donate. Thank you! ☕")

print("🤖 Bot is running... Press Ctrl+C to stop.")
bot.infinity_polling()