import asyncio
import os
import threading
import discord
from discord.ext import commands
from flask import Flask
import wavelink

# ==================== (سيرفر Flask للمراقبة و 24/7 Uptime) ====================
app = Flask('')


@app.route('/')
def home():
  return 'Lavalink Dedicated Music Bot is Online & Ready!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run)
  t.daemon = True
  t.start()


# ==================== (إعدادات البوت) ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# إعدادات الاتصال بسيرفر Lavalink
LAVALINK_HOST = os.getenv('LAVALINK_HOST', '127.0.0.1')
LAVALINK_PORT = int(os.getenv('LAVALINK_PORT', 2333))
LAVALINK_PASSWORD = os.getenv('LAVALINK_PASSWORD', 'youshallnotpass')


@bot.event
async def on_ready():
  print(f'✅ تم تسجيل الدخول بنجاح: {bot.user.name}')

  # ربط البوت بمحرك Lavalink
  node = wavelink.Node(
      uri=f'http://{LAVALINK_HOST}:{LAVALINK_PORT}', password=LAVALINK_PASSWORD
  )
  try:
    await wavelink.Pool.connect(nodes=[node], client=bot)
    print(
        '🚀 [Lavalink] تم الاتصال بنجاح بسيرفر الصوت:'
        f' {LAVALINK_HOST}:{LAVALINK_PORT}'
    )
  except Exception as e:
    print(f'❌ [Lavalink] تعذر الاتصال بسيرفر Lavalink: {e}')

  await bot.change_presence(
      activity=discord.Game(name='High-Quality Audio | Powered by Lavalink')
  )


@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEvent):
  print(
      f'📡 Lavalink Node [{payload.node.identifier}] جاهز تماماً لمعالجة الصوت!'
  )


# ==================== (الأوامر والفعاليات) ====================
@bot.event
async def on_message(message):
  if message.author.bot:
    return

  # 1. أمر إدخال البوت (setup / تعال / join / منشن)
  if bot.user.mentioned_in(message) or message.content.strip().lower() in [
      'setup',
      'تعال',
      'join',
  ]:
    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية أولاً!**'
      )

    voice_channel = message.author.voice.channel
    vc: wavelink.Player = message.guild.voice_client

    if vc:
      await vc.move_to(voice_channel)
    else:
      try:
        vc = await voice_channel.connect(cls=wavelink.Player)
        vc.inactive_timeout = 300  # الخروج التلقائي بعد 5 دقائق من الخمول
      except Exception as e:
        return await message.channel.send(
            f'❌ | **تعذر الاتصال بالروم:** `{e}`'
        )

    return await message.channel.send(
        f'✅ | **تم الدخول إلى الروم الصوتية:** `{voice_channel.name}`'
    )

  # 2. أمر التشغيل (ش [اسم الأغنية / رابط / قائمة تشغيل])
  if message.content.startswith('ش '):
    raw_query = message.content[2:].strip()
    if not raw_query:
      return await message.channel.send(
          '❌ | **يرجى كتابة اسم الأغنية أو الرابط بعد كلمة "ش"!**'
      )

    if not message.author.voice:
      return await message.channel.send(
          '❌ | **يجب أن تكون متصلاً بروم صوتية أولاً!**'
      )

    voice_channel = message.author.voice.channel
    vc: wavelink.Player = message.guild.voice_client

    if not vc:
      try:
        vc = await voice_channel.connect(cls=wavelink.Player)
        vc.inactive_timeout = 300
      except Exception as e:
        return await message.channel.send(
            f'❌ | **تعذر الاتصال بالروم الصوتية:** `{e}`'
        )
    elif vc.channel != voice_channel:
      await vc.move_to(voice_channel)

    try:
      async with message.channel.typing():
        # البحث المباشر: إذا كان رابطاً يتم جلب الرابط، وإذا كان اسماً يتم البحث في SoundCloud مباشرة لضمان العمل
        if raw_query.startswith(('http://', 'https://')):
          tracks = await wavelink.Playable.search(raw_query)
        else:
          tracks = await wavelink.Playable.search(
              raw_query, source=wavelink.Search.scsearch
          )

        if not tracks:
          return await message.channel.send(
              '❌ | **لم يتم العثور على نتائج لبحثك!**'
          )

        # معالجة قوائم التشغيل (Playlist)
        if isinstance(tracks, wavelink.Playlist):
          added = await vc.queue.put_wait(tracks)
          embed = discord.Embed(
              description=(
                  '🎵 | **تم إضافة قائمة التشغيل:**'
                  f' **[{tracks.name}]({raw_query})** ({added} أغنية)'
              ),
              color=discord.Color.blue(),
          )
          await message.channel.send(embed=embed)
        else:
          track = tracks[0]
          await vc.queue.put_wait(track)

          if vc.is_playing():
            embed = discord.Embed(
                description=(
                    '📌 | **تم إضافتها إلى الطابور:**'
                    f' **[{track.title}]({track.uri})**'
                ),
                color=discord.Color.green(),
            )
            await message.channel.send(embed=embed)

        # إذا لم يكن هناك شيء يعمل حالياً، نبدأ تشغيل الطابور
        if not vc.is_playing():
          await vc.play(vc.queue.get())
          track = vc.current
          embed = discord.Embed(
              title='♪ Now Playing', color=discord.Color.from_rgb(255, 119, 0)
          )
          embed.description = (
              f'**[{track.title}]({track.uri})**\nبواسطة:'
              f' **{track.author}**\nبطلب من: `{message.author.name}`'
          )
          await message.channel.send(embed=embed)

    except Exception as e:
      await message.channel.send(
          f'❌ | **حدث خطأ أثناء معالجة الطلب:** `{e}`'
      )

  # 3. أمر التخطي (س)
  elif message.content.strip() == 'س':
    vc: wavelink.Player = message.guild.voice_client
    if vc and vc.is_playing():
      await vc.skip(force=True)
      await message.channel.send('⏭️ | **تم تخطي الأغنية بنجاح!**')
    else:
      await message.channel.send(
          '❌ | **لا توجد أي أغنية تعمل حالياً للتخطي.**'
      )

  await bot.process_commands(message)


# ==================== (التشغيل التنفيذي) ====================
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print(
        '❌ ERROR: لم يتم العثور على التوكن! يرجى ضبط المتغير DISCORD_TOKEN.'
    )
