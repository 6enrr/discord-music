import asyncio
import os
import threading
import discord
from discord.ext import commands
from flask import Flask
import yt_dlp

# ==================== (سيرفر Flask للتشغيل 24/7) ====================
app = Flask('')


@app.route('/')
def home():
  return 'Music Bot is Online and Streaming 24/7!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run)
  t.start()


# ==================== (إعدادات البوت) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# إعدادات yt-dlp عامة بدون أي كوكيز أو تقييد
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
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn -b:a 192k',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):

  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title')
    self.url = data.get('url')
    self.uploader = data.get('uploader', 'غير معروف')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=not stream)
    )
    if 'entries' in data:
      data = data['entries'][0]
    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(
        فكرة عبقرية ومريحة جداً يا وحش! فعلاً الابتعاد عن يوتيوب والاعتماد على **SoundCloud** يحل المشكلة من جذورها؛ البوت بيصير عام للكل، بدون تسجيل دخول، وبدون مشاكل حظر أو كابتشا، وكل شخص يقدر يشغل اللي بده إياه بحرية تامة.

كل ما علينا فعله هو تغيير محرك البحث الافتراضي في الكود من يوتيوب (`ytsearch`) إلى ساوند كلاود (`scsearch`)، بالإضافة إلى دعم الروابط المباشرة لأي منصة أخرى.

---

### الكود النهائي والكامل لـ `main.py` (يعمل حصرياً على SoundCloud والروابط العامة):

```python
import asyncio
import os
import threading
import discord
from discord.ext import commands
from flask import Flask
import yt_dlp

# ==================== (سيرفر Flask للتشغيل 24/7) ====================
app = Flask('')


@app.route('/')
def home():
  return 'Music Bot is Online and Streaming 24/7 via SoundCloud!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run)
  t.start()


# ==================== (إعدادات البوت) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# خيارات yt-dlp المخصصة لـ SoundCloud والمنصات المفتوحة
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
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn -b:a 192k',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):

  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title')
    self.url = data.get('url')
    self.uploader = data.get('uploader', 'غير معروف')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=not stream)
    )
    if 'entries' in data:
      data = data['entries'][0]
    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(
        discord.FFmpegPCMAudio(filename, **ffmpeg_options),
        data=data,
    )


queues = {}


@bot.event
async def on_ready():
  print(f'تم تسجيل الدخول بنجاح: {bot.user.name}')
  await bot.change_presence(
      activity=discord.Game(
          name='SoundCloud Bot | امنشني أو اكتب setup | ش [اسم الأغنية]'
      )
  )


async def play_next(guild_id, channel, loop_bot):
  if guild_id in queues and len(queues[guild_id]) > 0:
    next_url, author, ctx = queues[guild_id].pop(0)
    try:
      player = await YTDLSource.from_url(next_url, loop=loop_bot, stream=True)
      ctx.voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next(guild_id, channel, loop_bot), loop_bot
          ),
      )
      embed = discord.Embed(
          title='♪ Now Playing (SoundCloud)',
          color=discord.Color.from_rgb(255, 119, 0),
      )
      embed.description = f'**[{player.title}]({next_url})**\nby **{player.uploader}**\nRequested by `{author}`'
      await channel.send(embed=embed)
    except Exception as e:
      print(f'خطأ في تشغيل التالي: {e}')


@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # 1. إدخال البوت للروم عن طريق المنشن أو كتابة setup أو تعال
  if (
      bot.user.mentioned_in(message)
      or message.content.strip().lower() in ['setup', 'تعال', 'join']
  ):
    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية لكي أستطيع الدخول إليك!**'
      )

    voice_channel = message.author.voice.channel
    if message.guild.voice_client:
      await message.guild.voice_client.move_to(voice_channel)
    else:
      try:
        await voice_channel.connect()
      except Exception as e:
        return await message.channel.send(
            f'❌ | **تعذر الاتصال بالروم:** `{e}`'
        )

    return await message.channel.send(
        f'✅ | **تم الدخول إلى الروم بنجاح:** `{voice_channel.name}`'
    )

  # 2. أمر التشغيل والبحث عبر SoundCloud (ش [اسم الأغنية أو الرابط])
  if message.content.startswith('ش '):
    query = message.content[2:].strip()
    if not query:
      return await message.channel.send(
          '❌ | **يرجى كتابة اسم الأغنية أو الرابط بعد حرف ش!**'
      )

    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية أولاً!**'
      )

    voice_channel = message.author.voice.channel
    if not message.guild.voice_client:
      try:
        await voice_channel.connect()
      except Exception as e:
        return await message.channel.send(
            f'❌ | **تعذر الاتصال بالروم الصوتية:** `{e}`'
        )
    else:
      if message.guild.voice_client.channel != voice_channel:
        await message.guild.voice_client.move_to(voice_channel)

    # التحويل للبحث المباشر عبر ساوند كلاود بدلاً من يوتيوب
    search_query = query if query.startswith('http') else f'scsearch:{query}'

    try:
      async with message.channel.typing():
        player = await YTDLSource.from_url(
            search_query, loop=bot.loop, stream=True
        )

      guild_id = message.guild.id
      if (
          message.guild.voice_client.is_playing()
          or message.guild.voice_client.is_paused()
      ):
        if guild_id not in queues:
          queues[guild_id] = []
        queues[guild_id].append(
            (search_query, message.author.name, message.channel)
        )
        embed = discord.Embed(
            description=f'📌 | **تم إضافتها إلى الطابور:** **{player.title}**',
            color=discord.Color.green(),
        )
        await message.channel.send(embed=embed)
      else:
        message.guild.voice_client.play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(guild_id, message.channel, bot.loop), bot.loop
            ),
        )
        embed = discord.Embed(
            title='♪ Now Playing (SoundCloud)',
            color=discord.Color.from_rgb(255, 119, 0),
        )
        embed.description = f'**[{player.title}]({search_query})**\nby **{player.uploader}**\nRequested by `{message.author.name}`'
        await message.channel.send(embed=embed)
    except Exception as e:
      await message.channel.send(f'❌ | **حدث خطأ أثناء جلب الأغنية:** `{e}`')

  # 3. أمر التخطي (س)
  elif message.content.strip() == 'س':
    if message.guild.voice_client and message.guild.voice_client.is_playing():
      message.guild.voice_client.stop()
      await message.channel.send('⏭️ | **تم تخطي الأغنية بنجاح!**')
    else:
      await message.channel.send(
          '❌ | **لا توجد أي أغنية تعمل حالياً للتخطي.**'
      )

  await bot.process_commands(message)


if __name__ == '__main__':
  keep_alive()
  TOKEN = os.getenv('TOKEN')
  if TOKEN:
    bot.run(TOKEN)
