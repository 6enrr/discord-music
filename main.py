import asyncio
import os
import threading
import discord
from discord.ext import commands
import yt_dlp

# ==================== (سيرفر Flask للمراقبة) ====================
from flask import Flask

app = Flask('')


@app.route('/')
def home():
  return 'Music Bot is Online & Ready!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run)
  t.daemon = True
  t.start()


# ==================== (إعدادات البوت والطابور) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# خيارات yt-dlp مع إضافة دعم البروكسي المنزلي/الخارجي لتجاوز حظر ريلوي
# (استبدل 'http://YOUR_PROXY_IP:PORT' برابط البروكسي الحقيقي إن وجد، أو اتركه فارغاً)
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    # 'proxy': 'http://YOUR_PROXY_IP:PORT',  <-- ضع رابط البروكسي هنا إذا كان لديك بروكسي جاهز
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# نظام إدارة الطابور لكل سيرفر
guild_queues = {}


class MusicQueue:

  def __init__(self):
    self.queue = []


def get_queue(guild_id):
  if guild_id not in guild_queues:
    guild_queues[guild_id] = MusicQueue()
  return guild_queues[guild_id]


class YTDLSource(discord.PCMVolumeTransformer):

  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)
    self.data = data
    self.title = data.get('title')
    self.url = data.get('webpage_url')

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


async def play_next(ctx, vc):
  q = get_queue(ctx.guild.id)
  if len(q.queue) == 0:
    return

  next_player = q.queue.pop(0)

  def after_playing(error):
    if error:
      print(f'خطأ في المشغل: {error}')
    fut = asyncio.run_coroutine_threadsafe(play_next(ctx, vc), bot.loop)
    try:
      fut.result()
    except Exception as e:
      print(e)

  vc.play(next_player, after=after_playing)

  embed = discord.Embed(
      title='♪ تشغيل الآن', color=discord.Color.from_rgb(255, 119, 0)
  )
  embed.description = f'**[{next_player.title}]({next_player.url})**'
  await ctx.send(embed=embed)


@bot.event
async def on_ready():
  print(f'✅ تم تسجيل الدخول بنجاح: {bot.user.name}')
  print('🚀 [Bot] البوت جاهز تماماً وبدون أخطاء يوتيوب!')


@bot.event
async def on_message(message):
  if message.author.bot:
    return

  content = message.content.strip().lower()

  # 1. أمر الانضمام للروم الصوتية
  if bot.user.mentioned_in(message) or content in ['setup', 'تعال', 'join']:
    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية أولاً!**'
      )

    voice_channel = message.author.voice.channel
    if message.guild.voice_client:
      await message.guild.voice_client.move_to(voice_channel)
    else:
      await voice_channel.connect()

    return await message.channel.send(
        f'✅ | **تم الدخول إلى الروم الصوتية:** `{voice_channel.name}`'
    )

  # 2. أمر التشغيل (ش)
  if message.content.startswith('ش '):
    query = message.content[2:].strip()
    if not query:
      return await message.channel.send(
          '❌ | **يرجى كتابة اسم الأغنية أو الرابط بعد كلمة "ش"!**'
      )

    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية أولاً!**'
      )

    voice_channel = message.author.voice.channel
    vc = message.guild.voice_client

    if not vc:
      try:
        vc = await voice_channel.connect()
      except Exception as e:
        return await message.channel.send(
            f'❌ | **تعذر الاتصال بالروم الصوتية:** `{e}`'
        )
    elif vc.channel != voice_channel:
      await vc.move_to(voice_channel)

    async with message.channel.typing():
      try:
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        q = get_queue(message.guild.id)

        if vc.is_playing() or vc.is_paused():
          q.queue.append(player)
          embed = discord.Embed(
              description=(
                  '📌 | **تمت الإضافة إلى الطابور:**'
                  f' **[{player.title}]({player.url})** (الترتيب:'
                  f' {len(q.queue)})'
              ),
              color=discord.Color.green(),
          )
          await message.channel.send(embed=embed)
        else:

          def after_playing(error):
            if error:
              print(f'خطأ: {error}')
            fut = asyncio.run_coroutine_threadsafe(
                play_next(message, vc), bot.loop
            )
            try:
              fut.result()
            except Exception as e:
              print(e)

          vc.play(player, after=after_playing)
          embed = discord.Embed(
              title='♪ تشغيل الآن', color=discord.Color.from_rgb(255, 119, 0)
          )
          embed.description = f'**[{player.title}]({player.url})**'
          await message.channel.send(embed=embed)

      except Exception as e:
        await message.channel.send(
            f'❌ | **حدث خطأ أثناء جلب أو تشغيل الأغنية:**\n```{e}```'
        )

  # 3. أمر التخطي (س / skip)
  elif content in ['س', 'skip', 'تخطي']:
    vc = message.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
      vc.stop()
      await message.channel.send('⏭ | **تم تخطي الأغنية والانتقال للتالية!**')
    else:
      await message.channel.send(
          '❌ | **لا توجد أي أغنية تعمل حالياً للتخطي.**'
      )

  # 4. أمر الخروج والإيقاف
  elif content in ['وقف', 'stop', 'disconnect', 'طللع']:
    vc = message.guild.voice_client
    q = get_queue(message.guild.id)
    q.queue.clear()
    if vc and vc.is_connected():
      await vc.disconnect()
      await message.channel.send('🔌 | **تم إيقاف البوت وتفريغ الطابور والخروج.**')
    else:
      await message.channel.send('❌ | **البوت ليس متصلاً بأي روم صوتية أساساً.**')

  await bot.process_commands(message)


if __name__ == '__main__':
  keep_alive()
  TOKEN = os.getenv('DISCORDTOKEN')

  if TOKEN:
    bot.run(TOKEN)
  else:
    print('❌ ERROR: لم يتم العثور على التوكن!')
