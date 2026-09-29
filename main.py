import asyncio
import json
import os
import threading
import urllib.parse
import urllib.request
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
    self.title = data.get('title', 'أغنية غير معروفة')
    self.url = data.get('webpage_url', data.get('url', ''))
    self.uploader = data.get('uploader', 'غير معروف')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=not stream)
    )
    if 'entries' in data and data['entries']:
      data = data['entries'][0]
    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(
        discord.FFmpegPCMAudio(filename, **ffmpeg_options),
        data=data,
    )


queues = {}


async def resolve_smart_query(query, loop):
  """يحاول تشغيل رابط يوتيوب من المصدر الأصلي أولاً، وفي حال الحظر يتحول تلقائياً إلى SoundCloud"""
  query = query.strip()

  # 1. روابط يوتيوب -> محاولة المصدر الأصلي أولاً
  if 'youtube.com' in query or 'youtu.be' in query:
    clean_url = query.split('&list=')[0].split('?list=')[0]

    def test_yt():
      return ytdl.extract_info(clean_url, download=False)

    try:
      data = await loop.run_in_executor(None, test_yt)
      if data:
        return clean_url
    except Exception as e:
      print(
          f'YouTube Direct Blocked ({e}), switching to SoundCloud fallback...'
      )

    # التحويل الاحتياطي عند حظر يوتيوب عبر oEmbed
    oembed_url = f'https://www.youtube.com/oembed?url={urllib.parse.quote(clean_url, safe="")}&format=json'

    def fetch_yt_oembed():
      req = urllib.request.Request(
          oembed_url, headers={'User-Agent': 'Mozilla/5.0'}
      )
      with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode()).get('title')

    try:
      title = await loop.run_in_executor(None, fetch_yt_oembed)
      if title:
        return f'scsearch:{title}'
    except Exception as e:
      print(f'oEmbed YT Error: {e}')

  # 2. روابط سبوتيفاي -> استخراج العنوان عبر oEmbed والبحث في SoundCloud
  elif 'spotify.com' in query:
    oembed_url = f'https://open.spotify.com/oembed?url={urllib.parse.quote(query, safe="")}'

    def fetch_spotify():
      req = urllib.request.Request(
          oembed_url, headers={'User-Agent': 'Mozilla/5.0'}
      )
      with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode()).get('title')

    try:
      title = await loop.run_in_executor(None, fetch_spotify)
      if title:
        return f'scsearch:{title}'
    except Exception as e:
      print(f'oEmbed Spotify Error: {e}')

  # 3. روابط ساوند كلاود أو الروابط المباشرة
  elif query.startswith('http://') or query.startswith('https://'):
    return query

  # 4. البحث النصي العادي
  return f'scsearch:{query}'


@bot.event
async def on_ready():
  print(f'تم تسجيل الدخول بنجاح: {bot.user.name}')
  await bot.change_presence(
      activity=discord.Game(
          name='Multi-Platform Music | YouTube / Spotify / SoundCloud'
      )
  )


async def play_next(guild, channel, loop_bot):
  guild_id = guild.id
  if guild_id in queues and len(queues[guild_id]) > 0:
    next_query, author = queues[guild_id].pop(0)
    voice_client = guild.voice_client

    if not voice_client or not voice_client.is_connected():
      return

    try:
      player = await YTDLSource.from_url(
          next_query, loop=loop_bot, stream=True
      )
      voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next(guild, channel, loop_bot), loop_bot
          ),
      )
      embed = discord.Embed(
          title='♪ Now Playing', color=discord.Color.from_rgb(255, 119, 0)
      )
      embed.description = f'**[{player.title}]({player.url})**\nby **{player.uploader}**\nRequested by `{author}`'
      await channel.send(embed=embed)
    except Exception as e:
      print(f'خطأ في تشغيل التالي: {e}')
      await play_next(guild, channel, loop_bot)


@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # 1. إدخال البوت للروم الصوتية
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

  # 2. أمر التشغيل (ش [اسم الأغنية / رابط])
  if message.content.startswith('ش '):
    raw_query = message.content[2:].strip()
    if not raw_query:
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

    try:
      async with message.channel.typing():
        search_query = await resolve_smart_query(raw_query, bot.loop)
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
        queues[guild_id].append((search_query, message.author.name))
        embed = discord.Embed(
            description=f'📌 | **تم إضافتها إلى الطابور:** **{player.title}**',
            color=discord.Color.green(),
        )
        await message.channel.send(embed=embed)
      else:
        message.guild.voice_client.play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(message.guild, message.channel, bot.loop), bot.loop
            ),
        )
        embed = discord.Embed(
            title='♪ Now Playing', color=discord.Color.from_rgb(255, 119, 0)
        )
        embed.description = f'**[{player.title}]({player.url})**\nby **{player.uploader}**\nRequested by `{message.author.name}`'
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
