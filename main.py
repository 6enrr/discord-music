import asyncio
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import discord
from discord.ext import commands
from flask import Flask
import yt_dlp

# ==================== (سيرفر Flask للتشغيل 24/7 على Render) ====================
app = Flask('')


@app.route('/')
def home():
  return 'YouTube Music Bot is Online!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run)
  t.daemon = True
  t.start()


# ==================== (إعدادات البوت والـ Intents) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ==================== (إعدادات yt-dlp الاحتياطية المتبسطة) ====================
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
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn -b:a 192k',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


# ==================== (دالة استخراج الصوت عبر Piped API لتجاوز الحظر) ====================
def get_piped_audio_stream(url_or_query):
  """استخراج رابط الصوت المباشر من سيرفرات Piped الوسيطة لتخطي حظر Render نهائياً"""
  video_id = None

  # 1. استخراج الـ ID إذا كان الإدخال رابط يوتيوب
  if 'youtube.com' in url_or_query or 'youtu.be' in url_or_query:
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url_or_query)
    if match:
      video_id = match.group(1)
  else:
    # 2. إذا كان بحثاً نصياً، البحث داخل Piped API
    search_instances = [
        'https://pipedapi.kavin.rocks',
        'https://api.piped.private.coffee',
        'https://pipedapi.mha.fi',
    ]
    for instance in search_instances:
      try:
        req_url = f'{instance}/search?q={urllib.parse.quote(url_or_query)}&filter=all'
        req = urllib.request.Request(
            req_url, headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
          res = json.loads(resp.read().decode())
          items = res.get('items', [])
          if items and 'url' in items[0]:
            video_id = items[0]['url'].split('v=')[-1]
            break
      except Exception:
        continue

  if not video_id:
    return None

  # 3. جلب رابط الصوت المباشر بجودة عالية باستخدام الـ ID
  stream_instances = [
      'https://pipedapi.kavin.rocks',
      'https://api.piped.private.coffee',
      'https://pipedapi.mha.fi',
  ]

  for instance in stream_instances:
    try:
      api_url = f'{instance}/streams/{video_id}'
      req = urllib.request.Request(
          api_url, headers={'User-Agent': 'Mozilla/5.0'}
      )
      with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        audio_streams = [
            s
            for s in data.get('audioStreams', [])
            if s.get('url') and not s.get('videoOnly')
        ]
        if audio_streams:
          best_audio = sorted(
              audio_streams, key=lambda x: x.get('bitrate', 0), reverse=True
          )[0]
          return {
              'url': best_audio['url'],
              'title': data.get('title', 'أغنية من يوتيوب'),
              'uploader': data.get('uploader', 'YouTube Channel'),
              'webpage_url': f'https://www.youtube.com/watch?v={video_id}',
          }
    except Exception:
      continue

  return None


class YTDLSource(discord.PCMVolumeTransformer):

  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title', 'أغنية غير معروفة')
    self.url = data.get('webpage_url', data.get('url', ''))
    self.uploader = data.get('uploader', 'غير معروف')

  @classmethod
  async def from_url(cls, url_or_query, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()

    # المحاولة الأولى عبر Piped API (لتخطي حظر Render IPs بالكامل)
    audio_data = await loop.run_in_executor(
        None, lambda: get_piped_audio_stream(url_or_query)
    )

    if audio_data:
      return cls(
          discord.FFmpegPCMAudio(audio_data['url'], **ffmpeg_options),
          data=audio_data,
      )

    # المحاولة الثانية (Fallback) عبر yt-dlp الأساسي
    def extract_fallback():
      target = url_or_query
      if not (target.startswith('http://') or target.startswith('https://')):
        target = f'ytsearch:{target}'
      return ytdl.extract_info(target, download=False)

    data = await loop.run_in_executor(None, extract_fallback)
    if 'entries' in data and data['entries']:
      data = data['entries'][0]

    if not data or 'url' not in data:
      raise Exception('تعذر استخراج الصوت من يوتيوب.')

    return cls(
        discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data
    )


queues = {}


@bot.event
async def on_ready():
  print(f'✅ تم تسجيل الدخول بنجاح: {bot.user.name}', flush=True)


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
          title='♪ Now Playing (YouTube)', color=discord.Color.red()
      )
      embed.description = f'**[{player.title}]({player.url})**\nby **{player.uploader}**\nRequested by `{author}`'
      await channel.send(embed=embed)
    except Exception as e:
      await channel.send(f'❌ **خطأ في التشغيل:** `{e}`')
      await play_next(guild, channel, loop_bot)


@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # أمر الدخول للروم الصوتية
  if (
      bot.user.mentioned_in(message)
      or message.content.strip().lower() in ['setup', 'تعال', 'join']
  ):
    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية!**'
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

  # أمر التشغيل (ش)
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
        player = await YTDLSource.from_url(
            raw_query, loop=bot.loop, stream=True
        )

      guild_id = message.guild.id
      if (
          message.guild.voice_client.is_playing()
          or message.guild.voice_client.is_paused()
      ):
        if guild_id not in queues:
          queues[guild_id] = []
        queues[guild_id].append((raw_query, message.author.name))
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
            title='♪ Now Playing (YouTube)', color=discord.Color.red()
        )
        embed.description = f'**[{player.title}]({player.url})**\nby **{player.uploader}**\nRequested by `{message.author.name}`'
        await message.channel.send(embed=embed)
    except Exception as e:
      channel_error_msg = f'❌ **خطأ أثناء تشغيل يوتيوب:**\n```{str(e)}```'
      await message.channel.send(channel_error_msg)

  # أمر التخطي (س)
  elif message.content.strip() == 'س':
    if message.guild.voice_client and message.guild.voice_client.is_playing():
      message.guild.voice_client.stop()
      await message.channel.send('⏭️ | **تم تخطي الأغنية بنجاح!**')
    else:
      await message.channel.send(
          '❌ | **لا توجد أي أغنية تعمل حالياً للتخطي.**'
      )

  await bot.process_commands(message)


# ==================== (تشغيل البوت) ====================
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('❌ ERROR: لم يتم العثور على التوكن في البيئة!', flush=True)
