import asyncio
import os
from threading import Thread
import discord
from discord.ext import commands
from flask import Flask
import yt_dlp

# ==================== (سيرفر Flask لإبقاء البوت شغالاً) ====================
app = Flask('')


@app.route('/')
def home():
  return 'Bot is alive!'


def run_flask():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = Thread(target=run_flask)
  t.daemon = True
  t.start()


# ==================== (البحث عن الكوكيز) ====================
cookie_path = None
possible_paths = ['/etc/secrets/cookies.txt', 'cookies.txt']

for path in possible_paths:
  if os.path.exists(path):
    cookie_path = path
    break

# ==================== (إعدادات البوت و yt-dlp) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb', 'ios', 'android'],
        }
    },
}

if cookie_path:
  ytdl_format_options['cookiefile'] = cookie_path
  print(f'✅ [Cookies] تم العثور على ملف الكوكيز واستخدامه من: {cookie_path}')
else:
  print('⚠️ [Cookies] لم يتم العثور على ملف cookies.txt (يعمل بدون كوكيز)')

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):

  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title')
    self.url = data.get('url')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=not stream)
    )

    if 'entries' in data:
      data = data['entries'][0]

    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


# ==================== (أوامر البوت) ====================
@bot.event
async def on_ready():
  print(f'🤖 تم تسجيل الدخول بنجاح باسم: {bot.user.name}')


@bot.command(name='play', aliases=['p', 'ش'])
async def play(ctx, *, url):
  if not ctx.author.voice:
    await ctx.send('❌ يجب أن تكون متواصلاً في روم صوتي أولاً!')
    return

  channel = ctx.author.voice.channel

  if ctx.voice_client is None:
    await channel.connect()
  elif ctx.voice_client.channel != channel:
    await ctx.voice_client.move_to(channel)

  async with ctx.typing():
    try:
      player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)

      if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

      ctx.voice_client.play(
          player,
          after=lambda e: print(f'Player error: {e}') if e else None,
      )
      await ctx.send(f'🎶 **جاري التشغيل الآن:** {player.title}')
    except Exception as e:
      await ctx.send(f'❌ **حدث خطأ أثناء جلب الأغنية:**\n```{e}```')


@bot.command(name='stop', aliases=['توقف'])
async def stop(ctx):
  if ctx.voice_client and ctx.voice_client.is_playing():
    ctx.voice_client.stop()
    await ctx.send('⏹️ تم إيقاف التشغيل.')
  else:
    await ctx.send('⚠️ لا يوجد شيء يعمل حالياً.')


@bot.command(name='leave', aliases=['غادر'])
async def leave(ctx):
  if ctx.voice_client:
    await ctx.voice_client.disconnect()
    await ctx.send('👋 تم الخروج من الروم الصوتي.')
  else:
    await ctx.send('⚠️ البوت ليس متواصلاً في أي روم صوتي.')


# ==================== (تشغيل البوت) ====================
if __name__ == '__main__':
  keep_alive()  # تشغيل خادم Flask
  token = os.environ.get('DISCORD_TOKEN')
  if token:
    bot.run(token)
  else:
    print('❌ خطأ: لم يتم العثور على DISCORD_TOKEN في متغيرات البيئة!')
