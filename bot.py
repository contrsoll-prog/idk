import io
import math
import os
from threading import Thread
import time
from datetime import datetime, timedelta
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
    command_prefix=["!", "#", ".", ""], intents=intents, help_command=None
)

COOLDOWN_TIME = 60
XP_PER_MESSAGE = 15
XP_PER_VOICE = 10

LEVEL_UP_CHANNEL_ID = 1546241742448234596
COMMAND_CHANNEL_ID = 1546188748621090926

cooldowns = {}

ADMIN_ROLE_IDS = [
    1546189327904804927,
]

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
# 🎯 تقييد الأوامر والصلاحيات
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

def check_admin_or_owner_user(member: discord.Member) -> bool:
    if not member.guild:
        return False
    if member.id == member.guild.owner_id:
        return True
    author_role_ids = [role.id for role in member.roles]
    return any(role_id in ADMIN_ROLE_IDS for role_id in author_role_ids)

def is_admin_or_owner():
    async def predicate(ctx):
        if check_admin_or_owner_user(ctx.author):
            return True
        raise commands.CheckFailure("❌ هذا الأمر مخصص للإدارة والمالك فقط!")
    return commands.check(predicate)

# --------------------------------------------------
# 2. قاعدة البيانات وتدريج صعوبة الـ XP
# --------------------------------------------------
async def init_db():
    async with aiosqlite.connect("leveling.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                voice_xp INTEGER DEFAULT 0,
                voice_level INTEGER DEFAULT 0,
                is_private INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_private INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()

# حساب الـ XP المطلوب بقانون صعوبة متدرج ومنطقي
def get_needed_xp(level: int) -> int:
    return int(100 + (15 * level) + (5 * (level ** 1.5)))

def format_number(num: int) -> str:
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M".replace(".0M", "M")
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K".replace(".0K", "K")
    return str(num)

async def log_xp_gain(user_id: int, amount: int):
    async with aiosqlite.connect("leveling.db") as db:
        await db.execute(
            "INSERT INTO xp_logs (user_id, amount, timestamp) VALUES (?, ?, ?)",
            (user_id, amount, datetime.utcnow())
        )
        await db.commit()

# --------------------------------------------------
# 3. صانع بطاقة Rank Card
# --------------------------------------------------
async def generate_dual_rank_card(
    member: discord.Member,
    text_data: tuple,
    voice_data: tuple,
    guild: discord.Guild,
) -> io.BytesIO:
    text_lvl, text_xp, text_needed, text_rank, text_total = text_data
    voice_lvl, voice_xp, voice_needed, voice_rank, voice_total = voice_data

    width, height = 850, 320
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    bg = Image.new("RGBA", (width, height), (22, 22, 29, 240))
    bg_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(bg_mask).rounded_rectangle(
        [(0, 0), (width, height)], radius=25, fill=255
    )

    image.paste(bg, (0, 0), bg_mask)
    draw = ImageDraw.Draw(image)

    wave_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wave_draw = ImageDraw.Draw(wave_overlay)
    wave_draw.ellipse([(250, -50), (950, 450)], fill=(108, 63, 196, 120))
    wave_draw.ellipse([(400, 100), (900, 500)], fill=(75, 45, 145, 160))
    image.paste(wave_overlay, (0, 0), bg_mask)

    # صورة الشخصية
    try:
        avatar_bytes = await member.display_avatar.with_format("png").read()
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((190, 190))
        mask = Image.new("L", (190, 190), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 190, 190), fill=255)
        draw.ellipse((35, 45, 235, 245), fill=(255, 255, 255, 255))
        image.paste(avatar_img, (40, 50), mask)
    except Exception:
        pass

    # صورة السيرفر المصغرة
    if guild and guild.icon:
        try:
            icon_bytes = await guild.icon.with_format("png").read()
            icon_img = Image.open(io.BytesIO(icon_bytes)).convert("RGBA").resize((45, 45))
            icon_mask = Image.new("L", (45, 45), 0)
            ImageDraw.Draw(icon_mask).ellipse((0, 0, 45, 45), fill=255)
            draw.ellipse((368, 18, 418, 68), fill=(255, 255, 255, 255))
            image.paste(icon_img, (370, 20), icon_mask)
        except Exception:
            pass

    try:
        font_name = ImageFont.truetype("arial.ttf", 34)
        font_lvl = ImageFont.truetype("arial.ttf", 36)
        font_sub = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        font_name = font_lvl = font_sub = font_small = ImageFont.load_default()

    display_name = member.display_name
    if len(display_name) > 16:
        display_name = display_name[:14] + ".."
    draw.text((430, 22), display_name, fill=(255, 255, 255, 255), font=font_name)

    # القسم الكتابي 💬
    draw.text((320, 85), "LVL", fill=(200, 200, 220, 255), font=font_small)
    draw.text((315, 105), str(text_lvl), fill=(255, 255, 255, 255), font=font_lvl)

    draw.rectangle([(380, 105), (410, 125)], fill=(255, 255, 255, 255))
    draw.polygon([(385, 125), (385, 133), (393, 125)], fill=(255, 255, 255, 255))

    draw.text((440, 95), f"Rank: #{text_rank}", fill=(210, 210, 230, 255), font=font_sub)
    draw.text((680, 95), f"Total: {format_number(text_total)}", fill=(210, 210, 230, 255), font=font_sub)

    bx, by, bw, bh = 440, 122, 370, 28
    draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=14, fill=(40, 42, 54, 230))
    prog_text = max(0.02, min(1.0, text_xp / text_needed)) if text_needed > 0 else 0.02
    draw.rounded_rectangle([(bx, by), (bx + int(bw * prog_text), by + bh)], radius=14, fill=(108, 100, 115, 255))
    draw.text((bx + 110, by + 3), f"{text_xp} / {text_needed}", fill=(255, 255, 255, 255), font=font_sub)

    # القسم الصوتي 🎤
    draw.text((320, 185), "LVL", fill=(200, 200, 220, 255), font=font_small)
    draw.text((320, 205), str(voice_lvl), fill=(255, 255, 255, 255), font=font_lvl)

    draw.rounded_rectangle([(387, 203), (397, 222)], radius=5, fill=(255, 255, 255, 255))
    draw.arc([(382, 210), (402, 225)], start=0, end=180, fill=(255, 255, 255, 255), width=2)
    draw.line([(392, 225), (392, 230)], fill=(255, 255, 255, 255), width=2)

    draw.text((440, 195), f"Rank: #{voice_rank}", fill=(210, 210, 230, 255), font=font_sub)
    draw.text((680, 195), f"Total: {format_number(voice_total)}", fill=(210, 210, 230, 255), font=font_sub)

    by_v = 222
    draw.rounded_rectangle([(bx, by_v), (bx + bw, by_v + bh)], radius=14, fill=(40, 42, 54, 230))
    prog_voice = max(0.02, min(1.0, voice_xp / voice_needed)) if voice_needed > 0 else 0.02
    draw.rounded_rectangle([(bx, by_v), (bx + int(bw * prog_voice), by_v + bh)], radius=14, fill=(108, 100, 115, 255))
    draw.text((bx + 120, by_v + 3), f"{voice_xp} / {voice_needed}", fill=(255, 255, 255, 255), font=font_sub)

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

    all_level_roles = [get_role_object(guild, i) for i in LEVEL_ROLES.values() if get_role_object(guild, i)]
    target_role = get_role_object(guild, LEVEL_ROLES[target_level]) if target_level else None

    roles_to_remove = [r for r in member.roles if r in all_level_roles and r != target_role]
    if roles_to_remove:
        try: await member.remove_roles(*roles_to_remove)
        except Exception: pass

    if target_role and target_role not in member.roles:
        try: await member.add_roles(target_role)
        except Exception: pass

# --------------------------------------------------
# 5. الأحداث والـ Voice XP
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

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    content_str = message.content.strip().lower()
    parts = content_str.split()
    first_word = parts[0] if parts else ""

    # 1. اختصار R / r (عرض الرتبة)
    if first_word in ["r", "!r", "#r", ".r"]:
        target_member = message.author
        if len(message.mentions) > 0:
            target_member = message.mentions[0]
        elif len(parts) > 1 and parts[1].isdigit():
            target_member = message.guild.get_member(int(parts[1])) or message.author
        ctx = await bot.get_context(message)
        await rank_command(ctx, target_member)
        return

    # 2. اختصار T / t (عرض المتصدرين)
    if first_word in ["t", "!t", "#t", ".t", "top", "توب"]:
        period = "all"
        if len(parts) > 1:
            if parts[1] in ["daily", "يومي", "اليوم"]: period = "daily"
            elif parts[1] in ["weekly", "اسبوعي", "أسبوعي", "الأسبوع"]: period = "weekly"
            elif parts[1] in ["monthly", "شهري", "الشهر"]: period = "monthly"
        ctx = await bot.get_context(message)
        await top_command(ctx, period)
        return

    # احتساب نقاط الـ XP
    user_id = message.author.id
    now = time.time()

    if user_id not in cooldowns or (now - cooldowns[user_id]) >= COOLDOWN_TIME:
        cooldowns[user_id] = now
        async with aiosqlite.connect("leveling.db") as db:
            async with db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()

            if not row:
                xp, level = XP_PER_MESSAGE, 0
                await db.execute("INSERT INTO users (user_id, xp, level) VALUES (?, ?, ?)", (user_id, xp, level))
            else:
                xp, level = row[0] + XP_PER_MESSAGE, row[1]
                needed_xp = get_needed_xp(level)

                if xp >= needed_xp:
                    old_level = level
                    level += 1
                    xp -= needed_xp
                    level_channel = bot.get_channel(LEVEL_UP_CHANNEL_ID) or message.channel
                    if level_channel:
                        await level_channel.send(f"🎉 تهانينا {message.author.mention}! لقد ارتفعت إلى **Level {level}**!")
                    await check_role_rewards(message.author, level)

                await db.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (xp, level, user_id))
            await db.commit()
            await log_xp_gain(user_id, XP_PER_MESSAGE)

    await bot.process_commands(message)

@tasks.loop(minutes=1)
async def voice_xp_loop():
    async with aiosqlite.connect("leveling.db") as db:
        for guild in bot.guilds:
            for vc in guild.voice_channels:
                real_members = [m for m in vc.members if not m.bot]
                if len(real_members) < 2: continue

                for member in real_members:
                    if member.voice.self_deaf or member.voice.deaf: continue
                    async with db.execute("SELECT voice_xp, voice_level FROM users WHERE user_id = ?", (member.id,)) as cursor:
                        row = await cursor.fetchone()

                    if not row or row[0] is None:
                        await db.execute("INSERT OR REPLACE INTO users (user_id, voice_xp, voice_level) VALUES (?, ?, ?)", (member.id, XP_PER_VOICE, 0))
                    else:
                        v_xp, v_level = row[0] + XP_PER_VOICE, row[1]
                        if v_xp >= get_needed_xp(v_level):
                            v_level += 1
                            v_xp -= get_needed_xp(v_level)
                        await db.execute("UPDATE users SET voice_xp = ?, voice_level = ? WHERE user_id = ?", (v_xp, v_level, member.id))
                    await log_xp_gain(member.id, XP_PER_VOICE)
        await db.commit()

# --------------------------------------------------
# 6. الأوامر وقراءة البطاقة وإدارة الخصوصية
# --------------------------------------------------
async def rank_command(ctx, member: discord.Member = None):
    member = member or ctx.author

    async with aiosqlite.connect("leveling.db") as db:
        # فحص إعداد الخصوصية
        async with db.execute("SELECT is_private FROM users WHERE user_id = ?", (member.id,)) as cursor:
            priv_row = await cursor.fetchone()
            is_private = priv_row[0] if priv_row else 0

        # حظر الرؤية إن كان البروفايل مقفولاً وكان الطالب عضواً عادياً
        if is_private and ctx.author.id != member.id and not check_admin_or_owner_user(ctx.author):
            await ctx.send("🔒 هذا العضو قام بقفل ملفه الشخصي ولا يمكن رؤية مستواه إلا للإدارة والمالك!")
            return

        # بيانات الكتابي
        async with db.execute("SELECT xp, level FROM users WHERE user_id = ?", (member.id,)) as cursor:
            row_text = await cursor.fetchone()

        # بيانات الصوتي
        async with db.execute("SELECT voice_xp, voice_level FROM users WHERE user_id = ?", (member.id,)) as cursor:
            row_voice = await cursor.fetchone()

        # الترتيب الكتابي
        async with db.execute("SELECT user_id FROM users ORDER BY level DESC, xp DESC") as cursor:
            all_text = await cursor.fetchall()
            text_rank = next((i for i, u in enumerate(all_text, 1) if u[0] == member.id), 1)

        # الترتيب الصوتي
        async with db.execute("SELECT user_id FROM users ORDER BY voice_level DESC, voice_xp DESC") as cursor:
            all_voice = await cursor.fetchall()
            voice_rank = next((i for i, u in enumerate(all_voice, 1) if u[0] == member.id), 1)

    text_xp = row_text[0] if row_text else 0
    text_lvl = row_text[1] if row_text else 0
    text_needed = get_needed_xp(text_lvl)
    text_total = (text_lvl * 500) + text_xp

    voice_xp = row_voice[0] if (row_voice and row_voice[0]) else 0
    voice_lvl = row_voice[1] if (row_voice and row_voice[1]) else 0
    voice_needed = get_needed_xp(voice_lvl)
    voice_total = (voice_lvl * 500) + voice_xp

    async with ctx.typing():
        img_buffer = await generate_dual_rank_card(
            member,
            (text_lvl, text_xp, text_needed, text_rank, text_total),
            (voice_lvl, voice_xp, voice_needed, voice_rank, voice_total),
            ctx.guild,
        )
        file = discord.File(fp=img_buffer, filename="rank.png")
        await ctx.send(file=file)

@bot.command(name="privacy", aliases=["قفلي", "قفل", "خصوصية"])
async def toggle_privacy(ctx):
    async with aiosqlite.connect("leveling.db") as db:
        async with db.execute("SELECT is_private FROM users WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
        
        new_status = 1 if not row or row[0] == 0 else 0
        await db.execute("INSERT OR REPLACE INTO users (user_id, is_private) VALUES (?, ?)", (ctx.author.id, new_status))
        await db.commit()

    msg = "🔒 تم **قفل** بطاقتك التعرفية! لن يستطيع أحد رؤيتها غيرك والإدارة." if new_status else "🔓 تم **فتح** بطاقتك التعرفية للجميع!"
    await ctx.send(msg)

async def top_command(ctx, time_frame: str = "all"):
    async with aiosqlite.connect("leveling.db") as db:
        if time_frame == "all":
            title = "🏆 قائمة المتصدرين (الكلي)"
            async with db.execute("SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
        else:
            now = datetime.utcnow()
            if time_frame == "daily":
                title = "📅 قائمة المتصدرين (اليومي)"
                start_time = now - timedelta(days=1)
            elif time_frame == "weekly":
                title = "📆 قائمة المتصدرين (الأسبوعي)"
                start_time = now - timedelta(weeks=1)
            elif time_frame == "monthly":
                title = "🗓️ قائمة المتصدرين (الشهري)"
                start_time = now - timedelta(days=30)

            async with db.execute("""
                SELECT user_id, SUM(amount) as total_xp 
                FROM xp_logs 
                WHERE timestamp >= ? 
                GROUP BY user_id 
                ORDER BY total_xp DESC 
                LIMIT 10
            """, (start_time,)) as cursor:
                rows = await cursor.fetchall()

    if not rows:
        await ctx.send("لا يوجد متصدرون في هذه الفترة حتى الآن.")
        return

    embed = discord.Embed(title=title, color=discord.Color.from_rgb(108, 63, 196))
    description = ""

    for idx, row in enumerate(rows, 1):
        user_id = row[0]
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"عضو مغادر ({user_id})"
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"

        if time_frame == "all":
            level, xp = row[1], row[2]
            description += f"{medal} **{name}** — Level `{level}` | `{format_number(xp)} XP`\n"
        else:
            gained_xp = row[1]
            description += f"{medal} **{name}** — مكتسب: `{format_number(gained_xp)} XP`\n"

    embed.description = description
    await ctx.send(embed=embed)

# --------------------------------------------------
# 7. تشغيل البوت
# --------------------------------------------------
token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ لم يتم العثور على التوكن في Environment Variables!")
