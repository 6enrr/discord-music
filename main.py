import asyncio
import os
import threading
import discord
from discord.ext import commands
import yt_dlp

# ==================== (سيرفر Flask للمراقبة وحفظ النشاط) ====================
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

# التعديل النهائي الصارم لتجاوز حظر يوتيوب والصيغ
ytdl_format_options = {
    'format': 'bestaudio',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    'extractor_args': {'youtube': {'player_client': ['android']}},
}

ffmpeg_options = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    ),
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

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
    if '&list=' in url:
      url = url.split('&list=')[0]

    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=not stream)
    )

    if 'entries' in data:
      data = data['entries'][0]

    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


@bot.event
async def on_ready():
  print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
  print('Bot is ready and connected to Discord!')


async def play_next(ctx):
  q = get_queue(ctx.guild.id)
  if len(q.queue) > 0:
    next_url, next_title = q.queue.pop(0)
    try:
      player = await YTDLSource.from_url(next_url, loop=bot.loop, stream=True)
      ctx.voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next(ctx), bot.loop
          ),
      )
      await ctx.send(f'🎶 **جاري تشغيل الآن:** `{player.title}`')
    except Exception as e:
      await ctx.send(f'❌ حدث خطأ أثناء تشغيل الأغنية التالية: {e}')
      await play_next(ctx)
  else:
    if ctx.voice_client:
      await ctx.voice_client.disconnect()


@bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
  if not ctx.author.voice:
    await ctx.send('❌ يجب أن تكون في روم صوتية لتشغيل الموسيقى!')
    return

  channel = ctx.author.voice.channel
  if ctx.voice_client is None:
    await channel.connect()
  elif ctx.voice_client.channel != channel:
    await ctx.move_to(channel)

  async with ctx.typing():
    try:
      player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
    except Exception as e:
      await ctx.send(f'❌ **حدث خطأ أثناء جلب أو تشغيل الأغنية:**\n```{e}```')
      return

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
      q = get_queue(ctx.guild.id)
      q.queue.append((url, player.title))
      await ctx.send(
          f'📥 **تمت إضافة الأغنية إلى الطابور:** `{player.title}` (الترتيب:'
          f' {len(q.queue)})'
      )
    else:
      ctx.voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next(ctx), bot.loop
          ),
      )
      await ctx.send(f'🎶 **جاري تشغيل الآن:** `{player.title}`')


@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
  if ctx.voice_client and ctx.voice_client.is_playing():
    ctx.voice_client.stop()
    await ctx.send('⏭️ **تم تخطي الأغنية!**')
  else:
    await ctx.send('❌ لا توجد أغنية قيد التشغيل حالياً لتخطيها.')


@bot.command(name='queue', aliases=['q'])
async def queue_info(ctx):
  q = get_queue(ctx.guild.id)
  if not q.queue:
    await ctx.send('📭 طابور التشغيل فارغ حالياً.')
    return

  embed = discord.Embed(title='🎶 طابور التشغيل الحالي', color=discord.Color.blue())
  queue_list = ''
  for i, (_, title) in enumerate(q.queue, 1):
    queue_list += f'**{i}.** {title}\n'
  embed.description = queue_list
  await ctx.send(embed=embed)


@bot.command(name='stop')
async def stop(ctx):
  if ctx.voice_client:
    q = get_queue(ctx.guild.id)
    q.queue.clear()
    await ctx.voice_client.disconnect()
    await ctx.send('🛑 **تم إيقاف البوت ومسح الطابور وخروج الروم.**')


# تشغيل سيرفر الـ Flask وحفظ النشاط
keep_alive()
TOKEN = os.environ.get('DISCORDTOKEN')
bot.run(TOKEN)
