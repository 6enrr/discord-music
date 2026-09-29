import os
import asyncio
from threading import Thread
from flask import Flask
import discord
from discord.ext import commands
import yt_dlp

# --- 1. خادم Flask لإبقاء البوت نشطاً على Render ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. إعدادات بوت ديسكورد ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. إعدادات yt-dlp و FFmpeg ---
COOKIE_PATH = '/etc/secrets/cookies.txt'

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
}

# إضافة ملف الكوكيز تلقائياً إذا كان موجوداً على السيرفر
if os.path.exists(COOKIE_PATH):
    YDL_OPTIONS['cookiefile'] = COOKIE_PATH
    print(f"Loaded cookies from {COOKIE_PATH}")

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# --- 4. أحداث وأوامر البوت ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("❌ يجب أن تكون في روم صوتي أولاً!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    async with ctx.typing():
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(search, download=False)
            )

            if 'entries' in data:
                data = data['entries'][0]

            url = data['url']
            title = data.get('title', 'أغنية')

            source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)

            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()

            ctx.voice_client.play(source)
            await ctx.send(f"🎶 يتم الآن تشغيل: **{title}**")

        except Exception as e:
            await ctx.send(f"❌ حدث خطأ أثناء جلب الأغنية:\n```{e}```")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("⏹️ تم إيقاف التشغيل.")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 تم الخروج من الروم الصوتي.")

# --- 5. تشغيل البوت ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_TOKEN")  # تأكد من إضافة DISCORD_TOKEN في Environment Variables في Render
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("ERROR: DISCORD_TOKEN environment variable is not set!")
