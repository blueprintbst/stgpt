
from telegram import Bot
from config import TOKEN, CHAT_ID

async def send_telegram_message(text):
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='HTML')
