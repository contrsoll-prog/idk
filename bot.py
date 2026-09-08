import io
import os
from threading import Thread
import time
import aiosqlite
import discord
from discord.ext import commands, tasks
from flask import Flask
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------
# 🌐 0. سيرفر Flask للحفاظ على اتصال البوت (Keep Alive)
# --------------------------------------------------
app = Flask("")


@app.route("/")
def home():
  return "Bot is online!"


def run():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  Thread(target=run).start()


keep_alive()

# --------------------------------------------------
# 1. إعدادات البوت والـ Intents
# --------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=["!", "#", "."], intents=intents, help_command=None
)

COOLDOWN_TIME = 60  # كولد داون الرسائل (بالثواني)
XP_PER_MESSAGE = 15  # الـ XP لكل رسالة
XP_PER_VOICE = 10  # الـ XP لكل دقيقة في الروم الصوتي

LEVEL_UP_CHANNEL_ID = 1546241742448234596  # آيدي روم رسائل التلفيل والتهنئة
COMMAND_CHANNEL_ID = 1546188748621090926  # آيدي شات الأوامر المخصص

cooldowns = {}

# --------------------------------------------------
# 🔑 قائمة الـ IDs للرتب المسموح لها باستخدام أوامر الإدارة
# --------------------------------------------------
ADMIN_ROLE_IDS = [
    1546189327904804927,
]

# --- ربط المستويات بالأسماء المخصصة للرتب في سيرفرك ---
LEVEL_ROLES = {
    5: 1546239996082651267,
    10: 1546239973857034321,
    15: 1546239956031250493,
    20: 1546239934409736365,
    25: 1546239886221254837,
    35: 1546239858073145535,
    45: 1546239839316213881,
    50: 1546239823185186906,
    60: 1546239796865798164,
    70: 1546239777144184872,
    80: 1546239759536488489,
    90: 1546239740381110362,
    99: 1546244817745612871,
    100: 1546239698589188238,
    120: 1546239644419497994,
}


# --------------------------------------------------
# 🎯 تقييد جميع أوامر البوت بشات معين
# --------------------------------------------------
@bot.check
async def restrict_commands_to_channel(ctx):
  if not ctx.guild:
    return True

  if ctx.channel.id != COMMAND_CHANNEL_ID:
    raise commands.CheckFailure(
        f"⚠️ جميع أوامر البوت تعمل فقط في الروم المخصص: <#{COMMAND_CHANNEL_ID}>"
    )

  return True


# --------------------------------------------------
# 🛡️ دالة التحقق من الصلاحيات الإدارية
# --------------------------------------------------
def is_admin_or_owner():

  async def predicate(ctx):
    if not ctx.guild:
      return False

    if ctx.author.id == ctx.guild.owner_id:
      return True

    author_role_ids = [role.id for role in ctx.author.roles]
    if any(role_id in ADMIN_ROLE_IDS for role_id in author_role_ids):
      return True

    raise commands.CheckFailure(
        "❌ هذا الأمر مخصص لمالك السيرفر وللرتب الإدارية المحددة فقط!"
    )

  return commands.check(predicate)


# --------------------------------------------------
# 2. قاعدة البيانات وتنسيق الأرقام
# --------------------------------------------------
async def init_db():
  async with aiosqlite.connect("leveling.db") as db:
    await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0
            )
        """)
    await db.commit()


def get_needed_xp(level: int) -> int:
  return 5 * (level**2) + (50 * level) + 100


def format_number(num: int) -> str:
  if num >= 1_000_000:
    return f"{num / 1_000_000:.1f}M"
  elif num >= 1_000:
    return f"{num / 1_000:.1f}K"
  return str(num)


# --------------------------------------------------
# 3. صانع بطاقة Probot Rank Card
# --------------------------------------------------
async def generate_probot_rank_card(
    member: discord.Member, level: int, xp: int, needed_xp: int, rank: int
) -> io.BytesIO:
  width, height = 900, 260
  image = Image.new("RGBA", (width, height), (30, 31, 34, 255))
  draw = ImageDraw.Draw(image)

  draw.rounded_rectangle(
      [(15, 15), (width - 15, height - 15)], radius=20, fill=(43, 45, 49, 255)
  )

  try:
    avatar_bytes = await member.display_avatar.with_format("png").read()
    avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar_img = avatar_img.resize((140, 140))

    mask = Image.new("L", (140, 140), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, 140, 140), fill=255)

    draw.ellipse((35, 55, 185, 205), fill=(88, 101, 242, 255))
    image.paste(avatar_img, (38, 58), mask)
  except Exception:
    pass

  try:
    font_name = ImageFont.truetype("arial.ttf", 36)
    font_rank = ImageFont.truetype("arial.ttf", 30)
    font_xp = ImageFont.truetype("arial.ttf", 24)
  except IOError:
    font_name = font_rank = font_xp = ImageFont.load_default()

  name_text = member.display_name
  if len(name_text) > 14:
    name_text = name_text[:12] + ".."
  draw.text((210, 40), name_text, fill=(255, 255, 255, 255), font=font_name)

  info_text = f"RANK #{rank}   LEVEL {level}"
  draw.text((500, 45), info_text, fill=(88, 101, 242, 255), font=font_rank)

  xp_str = f"{format_number(xp)} / {format_number(needed_xp)} XP"
  draw.text((210, 105), xp_str, fill=(180, 185, 195, 255), font=font_xp)

  bar_x, bar_y, bar_w, bar_h = 210, 155, 640, 32
  draw.rounded_rectangle(
      [(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)],
      radius=16,
      fill=(60, 63, 69, 255),
  )

  progress = max(0.04, min(1.0, xp / needed_xp)) if needed_xp > 0 else 0.04
  filled_w = int(bar_w * progress)
  draw.rounded_rectangle(
      [(bar_x, bar_y), (bar_x + filled_w, bar_y + bar_h)],
      radius=16,
      fill=(88, 101, 242, 255),
  )

  buffer = io.BytesIO()
  image.save(buffer, format="PNG")
  buffer.seek(0)
  return buffer


# --------------------------------------------------
# 4. نظام تبديل الرتب المخصصة
# --------------------------------------------------
def get_role_object(guild: discord.Guild, identifier):
  if isinstance(identifier, int):
    return guild.get_role(identifier)
  return discord.utils.get(guild.roles, name=str(identifier))


async def check_role_rewards(member: discord.Member, new_level: int):
  guild = member.guild

  target_level = None
  for lvl in sorted(LEVEL_ROLES.keys(), reverse=True):
    if new_level >= lvl:
      target_level = lvl
      break

  all_level_roles = []
  for identifier in LEVEL_ROLES.values():
    role = get_role_object(guild, identifier)
    if role:
      all_level_roles.append(role)

  target_role = None
  if target_level:
    target_role = get_role_object(guild, LEVEL_ROLES[target_level])

  roles_to_remove = [
      r for r in member.roles if r in all_level_roles and r != target_role
  ]
  if roles_to_remove:
    try:
      await member.remove_roles(*roles_to_remove)
    except Exception:
      pass

  if target_role and target_role not in member.roles:
    try:
      await member.add_roles(target_role)
    except Exception:
      pass


# --------------------------------------------------
# 5. الأحداث والـ Voice XP مع Anti-AFK
# --------------------------------------------------
@bot.event
async def on_ready():
  await init_db()
  voice_xp_loop.start()
  print(f"✅ تم تشغيل البوت بنجاح باسم: {bot.user.name}")


@bot.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.CheckFailure):
    await ctx.send(str(error))
  elif isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("❌ يرجى التأكد من كتابة عناصر الأمر بشكل صحيح.")


@bot.event
async def on_message(message):
  if message.author.bot or not message.guild:
    return

  user_id = message.author.id
  now = time.time()

  if user_id not in cooldowns or (now - cooldowns[user_id]) >= COOLDOWN_TIME:
    cooldowns[user_id] = now

    async with aiosqlite.connect("leveling.db") as db:
      async with db.execute(
          "SELECT xp, level FROM users WHERE user_id = ?", (user_id,)
      ) as cursor:
        row = await cursor.fetchone()

      if not row:
        xp, level = XP_PER_MESSAGE, 0
        await db.execute(
            "INSERT INTO users (user_id, xp, level) VALUES (?, ?, ?)",
            (user_id, xp, level),
        )
      else:
        xp, level = row[0] + XP_PER_MESSAGE, row[1]
        needed_xp = get_needed_xp(level)

        if xp >= needed_xp:
          old_level = level
          level += 1
          xp -= needed_xp

          level_channel = (
              bot.get_channel(LEVEL_UP_CHANNEL_ID) or message.channel
          )
          if level_channel:
            await level_channel.send(
                f"🎉 تهانينا {message.author.mention}! لقد ارتفعت من المستوى"
                f" **Level {old_level}** إلى **Level {level}**!"
            )
          await check_role_rewards(message.author, level)

        await db.execute(
            "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
            (xp, level, user_id),
        )
      await db.commit()

  await bot.process_commands(message)


@tasks.loop(minutes=1)
async def voice_xp_loop():
  async with aiosqlite.connect("leveling.db") as db:
    for guild in bot.guilds:
      for vc in guild.voice_channels:
        real_members = [m for m in vc.members if not m.bot]

        if len(real_members) < 2:
          continue

        for member in real_members:
          if member.voice.self_deaf or member.voice.deaf:
            continue

          async with db.execute(
              "SELECT xp, level FROM users WHERE user_id = ?", (member.id,)
          ) as cursor:
            row = await cursor.fetchone()

          if not row:
            await db.execute(
                "INSERT INTO users (user_id, xp, level) VALUES (?, ?, ?)",
                (member.id, XP_PER_VOICE, 0),
            )
          else:
            xp, level = row[0] + XP_PER_VOICE, row[1]
            needed_xp = get_needed_xp(level)
            if xp >= needed_xp:
              old_level = level
              level += 1
              xp -= needed_xp

              level_channel = bot.get_channel(LEVEL_UP_CHANNEL_ID)
              if level_channel:
                await level_channel.send(
                    f"🎉 تهانينا {member.mention}! لقد ارتفعت من المستوى"
                    f" **Level {old_level}** إلى **Level {level}**!"
                )
              await check_role_rewards(member, level)

            await db.execute(
                "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
                (xp, level, member.id),
            )
    await db.commit()


# --------------------------------------------------
# 6. الأوامر العامة وأمر المساعدة
# --------------------------------------------------


@bot.command(name="help", aliases=["مساعدة", "الاوامر", "أوامر", "commands"])
async def help_command(ctx):
  embed = discord.Embed(
      title="📜 قائمة أوامر البوت",
      description="إليك جميع الأوامر المتاحة في البوت مقسمة حسب الصلاحيات:",
      color=discord.Color.from_rgb(88, 101, 242),
  )

  embed.add_field(
      name="👥 الأوامر العامة",
      value=(
          "`!rank` أو `!ليفلي` - عرض بطاقة المستوى والترتيب الخاص بك أو بعذو"
          " آخر.\n`!top` أو `!توب` - عرض قائمة أعلى 10 متصدرين في السيرفر."
      ),
      inline=False,
  )

  embed.add_field(
      name="🛠️ أوامر الإدارة (للمالك والرتب المحددة)",
      value=(
          "`!setlevel <@user> <level>` - تحديد مستوى عضو معين.\n`!addxp <@user>"
          " <amount>` - إضافة نقاط XP لعضو.\n`!resetuser <@user>` - تصفير"
          " مستوى ونقاط عضو بالكامل.\n`!test_system` أو `!تست` - فحص وتجربة"
          " شمولية لجميع ميزات البوت."
      ),
      inline=False,
  )

  embed.set_footer(
      text=f"طلب بواسطة: {ctx.author.display_name}",
      icon_url=ctx.author.display_avatar.url,
  )
  await ctx.send(embed=embed)


@bot.command(name="rank", aliases=["r", "lvl", "level", "رتبتي", "ليفلي"])
async def rank(ctx, member: discord.Member = None):
  member = member or ctx.author

  async with aiosqlite.connect("leveling.db") as db:
    async with db.execute(
        "SELECT xp, level FROM users WHERE user_id = ?", (member.id,)
    ) as cursor:
      row = await cursor.fetchone()

    if not row:
      await ctx.send("❌ لا توجد بيانات تلفيل مسجلة لهذا العضو حتى الآن.")
      return

    xp, level = row
    needed_xp = get_needed_xp(level)

    async with db.execute(
        "SELECT user_id FROM users ORDER BY level DESC, xp DESC"
    ) as cursor:
      all_users = await cursor.fetchall()
      user_rank = [i for i, u in enumerate(all_users, 1) if u[0] == member.id][
          0
      ]

  async with ctx.typing():
    img_buffer = await generate_probot_rank_card(
        member, level, xp, needed_xp, user_rank
    )
    file = discord.File(fp=img_buffer, filename="rank.png")
    await ctx.send(file=file)


@bot.command(name="top", aliases=["lb", "leaderboard", "توب", "المتصدرين"])
async def top(ctx):
  async with aiosqlite.connect("leveling.db") as db:
    async with db.execute(
        "SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC"
        " LIMIT 10"
    ) as cursor:
      rows = await cursor.fetchall()

  if not rows:
    await ctx.send("لا يوجد متصدرون حالياً.")
    return

  embed = discord.Embed(
      title="🏆 قائمة المتصدرين (Top Levels)",
      color=discord.Color.from_rgb(88, 101, 242),
  )
  description = ""
  for idx, (user_id, level, xp) in enumerate(rows, 1):
    member = ctx.guild.get_member(user_id)
    name = member.display_name if member else f"عضو مغادر ({user_id})"
    medal = (
        "🥇"
        if idx == 1
        else "🥈"
        if idx == 2
        else "🥉"
        if idx == 3
        else f"`#{idx}`"
    )
    description += (
        f"{medal} **{name}** — Level `{level}` | `{format_number(xp)} XP`\n"
    )

  embed.description = description
  await ctx.send(embed=embed)


# --------------------------------------------------
# 7. أوامر الإدارة المحمية
# --------------------------------------------------


@bot.command(name="setlevel", aliases=["setlvl", "set-level"])
@is_admin_or_owner()
async def setlevel(ctx, member: discord.Member, new_level: int):
  async with aiosqlite.connect("leveling.db") as db:
    await db.execute(
        "INSERT OR REPLACE INTO users (user_id, xp, level) VALUES (?, 0, ?)",
        (member.id, new_level),
    )
    await db.commit()
  await check_role_rewards(member, new_level)
  await ctx.send(
      f"⚙️ تم تعديل مستوى {member.mention} إلى **Level {new_level}** وتحديث"
      " رتبته."
  )


@bot.command(name="addxp", aliases=["add-xp"])
@is_admin_or_owner()
async def addxp(ctx, member: discord.Member, amount: int):
  async with aiosqlite.connect("leveling.db") as db:
    async with db.execute(
        "SELECT xp, level FROM users WHERE user_id = ?", (member.id,)
    ) as cursor:
      row = await cursor.fetchone()

    xp = (row[0] if row else 0) + amount
    level = row[1] if row else 0

    while xp >= get_needed_xp(level):
      xp -= get_needed_xp(level)
      level += 1

    await db.execute(
        "INSERT OR REPLACE INTO users (user_id, xp, level) VALUES (?, ?, ?)",
        (member.id, xp, level),
    )
    await db.commit()

  await check_role_rewards(member, level)
  await ctx.send(f"✅ تم إضافة **{amount} XP** لـ {member.mention}.")


@bot.command(name="resetuser")
@is_admin_or_owner()
async def resetuser(ctx, member: discord.Member):
  async with aiosqlite.connect("leveling.db") as db:
    await db.execute("DELETE FROM users WHERE user_id = ?", (member.id,))
    await db.commit()
  await check_role_rewards(member, 0)
  await ctx.send(
      f"🧹 تم تصفير بيانات {member.mention} بالكامل وسحب رتب التلفيل منه."
  )


# --------------------------------------------------
# 🧪 أمر الفحص والتست الشامل
# --------------------------------------------------
@bot.command(name="test_system", aliases=["تست", "اختبار"])
@is_admin_or_owner()
async def test_system(ctx):
  msg = await ctx.send("🔍 **جاري تشغيل الفحص الشامل واختبار الميزات...**")
  results = []

  try:
    async with aiosqlite.connect("leveling.db") as db:
      async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        count = (await cursor.fetchone())[0]
    results.append(
        f"✅ **قاعدة البيانات:** شغال بنجاح (المسجلين حالياً: `{count}` عضو)"
    )
  except Exception as e:
    results.append(f"❌ **قاعدة البيانات:** خطأ ({e})")

  bot_member = ctx.guild.me
  if bot_member.guild_permissions.manage_roles:
    results.append(
        "✅ **صلاحية إدارة الرتب:** البوت يمتلك صلاحية `Manage Roles` بنجاح."
    )
  else:
    results.append(
        "❌ **صلاحية إدارة الرتب:** البوت يفتقر لصلاحية `Manage Roles` (لن"
        " يستطيع إعطاء الرتب)."
    )

  missing_roles = []
  found_roles = []
  for lvl, role_id in LEVEL_ROLES.items():
    role = ctx.guild.get_role(role_id)
    if not role:
      missing_roles.append(f"Lvl {lvl}")
    else:
      found_roles.append(role)

  if missing_roles:
    results.append(
        f"⚠️ **الرتب المفقودة:** لم يتم العثور على: {', '.join(missing_roles)}"
    )
  else:
    results.append(
        f"✅ **الرتب:** جميع الرتب الـ `{len(LEVEL_ROLES)}` موجودة بالسيرفر."
    )

  if found_roles and bot_member.top_role.position <= max(
      r.position for r in found_roles
  ):
    results.append(
        "⚠️ **ترتيب رتبة البوت:** رتبة البوت أدنى من رتب التلفيل! يجب رفع رتبة"
        " البوت لأعلى قائمة الرتب في السيرفر ليعمل السحب/الإعطاء."
    )
  else:
    results.append(
        "✅ **ترتيب رتبة البوت:** رتبة البوت في موقع أعلى من رتب التلفيل (يستطيع"
        " والتعديل عليها)."
    )

  try:
    needed = get_needed_xp(1)
    await generate_probot_rank_card(ctx.author, 1, 50, needed, 1)
    results.append(
        "✅ **بطاقة الرتبة (Pillow):** توليد البطاقات يعمل بشكل ممتاز وبدون"
        " مشاكل."
    )
  except Exception as e:
    results.append(f"❌ **بطاقة الرتبة:** خطأ في النظام ({e})")

  try:
    first_lvl = list(LEVEL_ROLES.keys())[0]
    test_role = ctx.guild.get_role(LEVEL_ROLES[first_lvl])
    if test_role:
      await check_role_rewards(ctx.author, first_lvl)
      results.append(
          f"✅ **اختبار الرتب الحي:** تم اختبار إعطاء رتبة ({test_role.name})"
          " عليك بنجاح!"
      )
    else:
      results.append(
          "⚠️ **اختبار الرتب الحي:** تعذر العثور على الرتبة لتجربتها."
      )
  except Exception as e:
    results.append(f"❌ **اختبار الرتب الحي:** خطأ ({e})")

  embed = discord.Embed(
      title="📊 تقرير فحص وملاحظات نظام التلفيل",
      description="\n\n".join(results),
      color=(
          discord.Color.green()
          if all("❌" not in r for r in results)
          else discord.Color.gold()
      ),
  )
  embed.set_footer(text=f"طلب الفحص بواسطة: {ctx.author.display_name}")
  await msg.edit(content="✨ **اكتمل الفحص الشامل!**", embed=embed)


# --------------------------------------------------
# 8. تشغيل البوت عبر متغير البيئة
# --------------------------------------------------
token = os.environ.get("DISCORD_TOKEN")
if token:
  bot.run(token)
else:
  print("❌ لم يتم العثور على التوكن في Environment Variables!")