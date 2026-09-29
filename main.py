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
  t.daemon = True
  t.start()


# ==================== (الكشف التلقائي عن الكوكيز) ====================
cookie_path = None
if os.path.exists('/etc/secrets/cookies.txt'):
  cookie_path = '/etc/secrets/cookies.txt'
elif os.path.exists('cookies.txt'):
  cookie_path = 'cookies.txt'

# ==================== (إعدادات البوت و yt-dlp) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# خيارات yt-dlp المتطورة لتجاوز حظر يوتيوب على السيرفرات
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractor_args': {
        'youtube': {
            'player_client': ['android_vr', 'web_creator', 'ios', 'android'],
            'skip': ['hls', 'dash'],
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
  async def from_url(cls, url_or_query, *, loop=None, stream=True):
    loop = loop or asyncio.get_event_loop()

    def extract(target):
      return ytdl.extract_info(target, download=not stream)

    data = None

    # 1. محاولة التشغيل المباشر عبر يوتيوب
    try:
      data = await loop.run_in_executor(None, lambda: extract(url_or_query))
    except Exception as e:
      print(f'⚠️ فشل يوتيوب المباشر ({e})، جاري التحديد والتحويل البديل...')

    # إذا رجعت القائمة تحتوي على نتائج بحث يوتيوب
    if data and 'entries' in data and data['entries']:
      valid_entries = [e for e in data['entries'] if e]
      if valid_entries:
        data = valid_entries[0]
      else:
        data = None

    # 2. خطة الطوارئ: التحويل إلى SoundCloud مع فلترة ملفات DRM تلقائياً
    if not data or 'url' not in data:
      clean_search = (
          url_or_query.replace('ytsearch:', '').split('&')[0].split('?')[0]
      )
      sc_query = f'scsearch5:{clean_search}'
      print(f'🔄 جاري البحث المتقدم على SoundCloud: {sc_query}')

      sc_data = await loop.run_in_executor(None, lambda: extract(sc_query))

      if sc_data and 'entries' in sc_data:
        for entry in sc_data['entries']:
          if not entry:
            continue
          # تجنب مقاطع DRM المعتمدة في ساوند كلاود
          try:
            test_data = await loop.run_in_executor(
                None, lambda: extract(entry['webpage_url'])
            )
            if test_data and 'url' in test_data:
              data = test_data
              break
          except Exception:
            continue

    if not data or 'url' not in data:
      raise Exception(
          'تعذر جلب الصوت من يوتيوب أو SoundCloud. يرجى تجربة اسم آخر.'
      )

    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(
        discord.FFmpegPCMAudio(filename, **ffmpeg_options),
        data=data,
    )


queues = {}


async def resolve_smart_query(query, loop):
  query = query.strip()

  # رابط يوتيوب مباشر
  if 'youtube.com' in query or 'youtu.be' in query:
    return query.split('&list=')[0].split('?list=')[0]

  # رابط سبوتيفاي -> جلب العنوان والبحث
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
        return f'ytsearch:{title}'
    except Exception as e:
      print(f'Spotify Error: {e}')

  elif query.startswith('http://') or query.startswith('https://'):
    return query

  # البحث النصي المباشر
  return f'ytsearch:{query}'


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


# ==================== (تشغيل البوت) ====================
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print(
        '❌ ERROR: لم يتم العثور على التوكن! يرجى إضافته في Environment'
        ' Variables باسم DISCORD_TOKEN أو TOKEN.'
    )
