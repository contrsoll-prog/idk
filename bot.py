import io
import math
import os
from threading import Thread
import time
from datetime import datetime, timedelta, timezone
import aiosqlite
import sqlite3
import discord
from discord.ext import commands, tasks
from flask import Flask, request, render_template_string, redirect, url_for
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------
# 🌐 0. سيرفر Flask والداشبورد المطور لكل السيرفرات
# --------------------------------------------------
app = Flask("")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <title>لوحة تحكم البوت</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a24; color: white; padding: 20px; direction: rtl; }
        .container { max-width: 700px; margin: 0 auto; }
        .card { background: #2a2a3a; padding: 25px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        h2, h3 { color: #5865F2; margin-top: 0; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        input { width: 100%; padding: 10px; margin-top: 5px; border-radius: 6px; border: 1px solid #444; background: #1e1e2e; color: white; box-sizing: border-box; }
        button { width: 100%; padding: 12px; margin-top: 20px; border-radius: 6px; border: none; background: #5865F2; color: white; font-weight: bold; font-size: 16px; cursor: pointer; }
        button:hover { background: #4752C4; }
        .btn-danger { background: #ed4245; padding: 6px 12px; font-size: 12px; margin-top: 0; width: auto; }
        .btn-danger:hover { background: #c03537; }
        .alert { background: #2e7d32; padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 15px; }
        table { width: 100%; margin-top: 15px; border-collapse: collapse; }
        th, td { border: 1px solid #444; padding: 10px; text-align: center; }
        th { background: #1e1e2e; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h2>🎛️ إدارة السيرفرات</h2>
            <form method="GET" action="/">
                <label>ادخل ID السيرفر لتعديل إعداداته:</label>
                <input type="text" name="guild_id" value="{{ guild_id or '' }}" placeholder="مثال: 1309399614138351736" required>
                <button type="submit">جلب بيانات السيرفر 🔍</button>
            </form>
        </div>

        {% if guild_id %}
        {% if success %}
            <div class="alert">✅ تم حفظ الإعدادات بنجاح!</div>
        {% endif %}

        <div class="card">
            <h3>⚙️ إعدادات السيرفر الأساسية</h3>
            <form method="POST" action="/save_settings">
                <input type="hidden" name="guild_id" value="{{ guild_id }}">
                
                <label>ID روم الأوامر:</label>
                <input type="text" name="cmd_channel_id" value="{{ settings.cmd_channel_id or '' }}" placeholder="مثال: 1546188748621090926" required>

                <label>ID روم التنبيهات (الليفل أب):</label>
                <input type="text" name="level_channel_id" value="{{ settings.level_channel_id or '' }}" placeholder="مثال: 1546241742448234596">

                <label>IDs رتب الأدمن (افصل بينها بفاصلة ,):</label>
                <input type="text" name="admin_role_ids" value="{{ settings.admin_role_ids or '' }}" placeholder="مثال: 123456789,987654321">

                <button type="submit">حفظ الإعدادات الأساسية 💾</button>
            </form>
        </div>

        <div class="card">
            <h3>🎁 مكافآت المستويات (Level Roles)</h3>
            <form method="POST" action="/add_role">
                <input type="hidden" name="guild_id" value="{{ guild_id }}">
                <label>المستوى (Level):</label>
                <input type="number" name="level" placeholder="مثال: 5" required>
                
                <label>ID الرتبة (Role ID):</label>
                <input type="text" name="role_id" placeholder="مثال: 1546239996082651267" required>
                
                <button type="submit">إضافة رتبة ➕</button>
            </form>

            <table>
                <thead>
                    <tr>
                        <th>المستوى</th>
                        <th>ID الرتبة</th>
                        <th>إجراء</th>
                    </tr>
                </thead>
                <tbody>
                    {% for role in level_roles %}
                    <tr>
                        <td>{{ role.level }}</td>
                        <td>{{ role.role_id }}</td>
                        <td>
                            <form method="POST" action="/delete_role" style="margin:0;">
                                <input type="hidden" name="guild_id" value="{{ guild_id }}">
                                <input type="hidden" name="level" value="{{ role.level }}">
                                <button type="submit" class="btn-danger">حذف ❌</button>
                            </form>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="3">لا توجد رتب مضافة لهذا السيرفر بعد.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def get_db_connection():
    conn = sqlite3.connect("leveling.db", timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def home():
    guild_id = request.args.get("guild_id")
    success = request.args.get("success", False)
    settings = {}
    level_roles = []

    if guild_id and guild_id.isdigit():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (int(guild_id),))
        row = cursor.fetchone()
        if row:
            settings = dict(row)

        cursor.execute("SELECT level, role_id FROM server_roles WHERE guild_id = ? ORDER BY level ASC", (int(guild_id),))
        level_roles = [dict(r) for r in cursor.fetchall()]
        conn.close()

    return render_template_string(DASHBOARD_HTML, guild_id=guild_id, settings=settings, level_roles=level_roles, success=success)

@app.route("/save_settings", methods=["POST"])
def save_settings():
    guild_id = request.form.get("guild_id")
    cmd_channel_id = request.form.get("cmd_channel_id")
    level_channel_id = request.form.get("level_channel_id")
    admin_role_ids = request.form.get("admin_role_ids", "")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO server_settings (guild_id, cmd_channel_id, level_channel_id, admin_role_ids)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            cmd_channel_id=excluded.cmd_channel_id,
            level_channel_id=excluded.level_channel_id,
            admin_role_ids=excluded.admin_role_ids
    """, (int(guild_id), int(cmd_channel_id), int(level_channel_id) if level_channel_id else None, admin_role_ids))
    conn.commit()
    conn.close()

    return redirect(url_for("home", guild_id=guild_id, success=True))

@app.route("/add_role", methods=["POST"])
def add_role():
    guild_id = request.form.get("guild_id")
    level = request.form.get("level")
    role_id = request.form.get("role_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO server_roles (guild_id, level, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id
    """, (int(guild_id), int(level), int(role_id)))
    conn.commit()
    conn.close()

    return redirect(url_for("home", guild_id=guild_id, success=True))

@app.route("/delete_role", methods=["POST"])
def delete_role():
    guild_id = request.form.get("guild_id")
    level = request.form.get("level")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM server_roles WHERE guild_id = ? AND level = ?", (int(guild_id), int(level)))
    conn.commit()
    conn.close()

    return redirect(url_for("home", guild_id=guild_id, success=True))

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run, daemon=True).start()

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

COOLDOWN_TIME = 60
XP_PER_MESSAGE = 15
XP_PER_VOICE = 10

cooldowns = {}

# --------------------------------------------------
# 🎯 تقييد الأوامر والصلاحيات
# --------------------------------------------------
async def is_channel_allowed(ctx_or_message):
    if not ctx_or_message.guild:
        return True, None

    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        async with db.execute("SELECT cmd_channel_id FROM server_settings WHERE guild_id = ?", (ctx_or_message.guild.id,)) as cursor:
            row = await cursor.fetchone()

    if row and row[0]:
        allowed_channel_id = int(row[0])
        if ctx_or_message.channel.id != allowed_channel_id:
            return False, allowed_channel_id
    return True, None

@bot.check
async def restrict_commands_to_channel(ctx):
    allowed, allowed_channel_id = await is_channel_allowed(ctx)
    if not allowed:
        raise commands.CheckFailure(
            f"⚠️ جميع أوامر البوت تعمل فقط في الروم المخصص: <#{allowed_channel_id}>"
        )
    return True

async def check_admin_or_owner_user(member: discord.Member) -> bool:
    if not member.guild:
        return False
    if member.id == member.guild.owner_id:
        return True
    
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        async with db.execute("SELECT admin_role_ids FROM server_settings WHERE guild_id = ?", (member.guild.id,)) as cursor:
            row = await cursor.fetchone()
            
    if row and row[0]:
        admin_roles = [int(r.strip()) for r in row[0].split(",") if r.strip().isdigit()]
        author_role_ids = [role.id for role in member.roles]
        return any(role_id in admin_roles for role_id in author_role_ids)
    return False

# --------------------------------------------------
# 2. قاعدة البيانات ودعم تعدد السيرفرات
# --------------------------------------------------
async def init_db():
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id INTEGER PRIMARY KEY,
                cmd_channel_id INTEGER,
                level_channel_id INTEGER,
                admin_role_ids TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_roles (
                guild_id INTEGER,
                level INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                voice_xp INTEGER DEFAULT 0,
                voice_level INTEGER DEFAULT 0,
                is_private INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                amount INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

def get_needed_xp(level: int) -> int:
    return int(100 + (15 * level) + (5 * (level ** 1.5)))

def format_number(num: int) -> str:
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M".replace(".0M", "M")
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K".replace(".0K", "K")
    return str(num)

async def log_xp_gain(guild_id: int, user_id: int, amount: int):
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        await db.execute(
            "INSERT INTO xp_logs (guild_id, user_id, amount, timestamp) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, amount, datetime.now(timezone.utc))
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

    width, height = 900, 360
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    bg = Image.new("RGBA", (width, height), (22, 22, 29, 245))
    bg_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(bg_mask).rounded_rectangle(
        [(0, 0), (width, height)], radius=25, fill=255
    )

    image.paste(bg, (0, 0), bg_mask)
    draw = ImageDraw.Draw(image)

    wave_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wave_draw = ImageDraw.Draw(wave_overlay)
    wave_draw.ellipse([(250, -50), (1000, 500)], fill=(108, 63, 196, 120))
    wave_draw.ellipse([(420, 100), (950, 550)], fill=(75, 45, 145, 160))
    image.paste(wave_overlay, (0, 0), bg_mask)

    try:
        avatar_bytes = await member.display_avatar.with_format("png").read()
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((200, 200))
        mask = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 200, 200), fill=255)
        draw.ellipse((30, 75, 240, 285), fill=(255, 255, 255, 255))
        image.paste(avatar_img, (35, 80), mask)
    except Exception:
        pass

    def load_font(size):
        for font_path in ["arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf", "Ubuntu-R.ttf"]:
            try:
                return ImageFont.truetype(font_path, size)
            except IOError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    font_name = load_font(42)
    font_lvl = load_font(48)
    font_sub = load_font(26)
    font_small = load_font(22)
    font_bar = load_font(24)

    display_name = member.display_name
    if len(display_name) > 15:
        display_name = display_name[:13] + ".."
    draw.text((450, 20), display_name, fill=(255, 255, 255, 255), font=font_name)

    # --- 1. القسم الكتابي 💬 ---
    draw.text((275, 95), "LVL", fill=(180, 180, 210, 255), font=font_small)
    draw.text((275, 120), str(text_lvl), fill=(255, 255, 255, 255), font=font_lvl)

    # تم إزاحة أيقونة الشات لليمين (x=395 بدلاً من 345)
    draw.rounded_rectangle([(395, 120), (435, 150)], radius=6, fill=(255, 255, 255, 255))
    draw.polygon([(400, 150), (400, 162), (412, 150)], fill=(255, 255, 255, 255))

    draw.text((450, 95), f"Rank: #{text_rank}", fill=(230, 230, 245, 255), font=font_sub)
    draw.text((700, 95), f"Total: {format_number(text_total)}", fill=(230, 230, 245, 255), font=font_sub)

    bx, by, bw, bh = 450, 132, 410, 36
    draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=18, fill=(40, 42, 54, 230))
    prog_text = max(0.02, min(1.0, text_xp / text_needed)) if text_needed > 0 else 0.02
    draw.rounded_rectangle([(bx, by), (bx + int(bw * prog_text), by + bh)], radius=18, fill=(138, 90, 225, 255))
    draw.text((bx + 130, by + 4), f"{text_xp} / {text_needed}", fill=(255, 255, 255, 255), font=font_bar)

    # --- 2. القسم الصوتي 🎤 ---
    draw.text((275, 215), "LVL", fill=(180, 180, 210, 255), font=font_small)
    draw.text((275, 240), str(voice_lvl), fill=(255, 255, 255, 255), font=font_lvl)

    # تم إزاحة أيقونة المايك لليمين (x=407 بدلاً من 357)
    draw.rounded_rectangle([(407, 235), (423, 262)], radius=7, fill=(255, 255, 255, 255))
    draw.arc([(400, 245), (430, 268)], start=0, end=180, fill=(255, 255, 255, 255), width=3)
    draw.line([(415, 268), (415, 276)], fill=(255, 255, 255, 255), width=3)

    draw.text((450, 215), f"Rank: #{voice_rank}", fill=(230, 230, 245, 255), font=font_sub)
    draw.text((700, 215), f"Total: {format_number(voice_total)}", fill=(230, 230, 245, 255), font=font_sub)

    by_v = 252
    draw.rounded_rectangle([(bx, by_v), (bx + bw, by_v + bh)], radius=18, fill=(40, 42, 54, 230))
    prog_voice = max(0.02, min(1.0, voice_xp / voice_needed)) if voice_needed > 0 else 0.02
    draw.rounded_rectangle([(bx, by_v), (bx + int(bw * prog_voice), by_v + bh)], radius=18, fill=(138, 90, 225, 255))
    draw.text((bx + 130, by_v + 4), f"{voice_xp} / {voice_needed}", fill=(255, 255, 255, 255), font=font_bar)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --------------------------------------------------
# 4. الأحداث والأوامر
# --------------------------------------------------
async def check_role_rewards(member: discord.Member, new_level: int):
    guild = member.guild
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        async with db.execute("SELECT level, role_id FROM server_roles WHERE guild_id = ? ORDER BY level DESC", (guild.id,)) as cursor:
            server_roles = await cursor.fetchall()

    if not server_roles:
        return

    level_map = {row[0]: row[1] for row in server_roles}
    target_level = None
    for lvl in sorted(level_map.keys(), reverse=True):
        if new_level >= lvl:
            target_level = lvl
            break

    all_level_roles = [guild.get_role(r_id) for r_id in level_map.values() if guild.get_role(r_id)]
    target_role = guild.get_role(level_map[target_level]) if target_level else None

    # سحب جميع رتب المستويات السابقة التي لا يستحقها العضو
    roles_to_remove = [r for r in member.roles if r in all_level_roles and r != target_role]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove)
        except Exception:
            pass

    # إعطاء الرتبة المستحقة للمستوى الحالي
    if target_role and target_role not in member.roles:
        try:
            await member.add_roles(target_role)
        except Exception:
            pass

@bot.event
async def on_ready():
    await init_db()
    if not voice_xp_loop.is_running():
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

    # 0. فحص أمر الأوامر
    if first_word in ["أوامر", "اوامر", "!أوامر", "!اوامر", "#أوامر", "#اوامر", ".أوامر", ".اوامر", "help", "!help", "#help", ".help"]:
        allowed, allowed_channel_id = await is_channel_allowed(message)
        if not allowed:
            await message.channel.send(f"⚠️ جميع أوامر البوت تعمل فقط في الروم المخصص: <#{allowed_channel_id}>")
            return
        ctx = await bot.get_context(message)
        await help_command(ctx)
        return

    # 1. فحص اختصارات الرانك
    if first_word in ["r", "!r", "#r", ".r", "rank", "!rank", "#rank", ".rank", "رانك"]:
        allowed, allowed_channel_id = await is_channel_allowed(message)
        if not allowed:
            await message.channel.send(f"⚠️ جميع أوامر البوت تعمل فقط في الروم المخصص: <#{allowed_channel_id}>")
            return

        target_member = message.author
        if len(message.mentions) > 0:
            target_member = message.mentions[0]
        elif len(parts) > 1 and parts[1].isdigit():
            target_member = message.guild.get_member(int(parts[1])) or message.author
        ctx = await bot.get_context(message)
        await rank_command(ctx, target_member)
        return

    # 2. فحص اختصارات التوب
    if first_word in ["t", "!t", "#t", ".t", "top", "!top", "#top", ".top", "توب"]:
        allowed, allowed_channel_id = await is_channel_allowed(message)
        if not allowed:
            await message.channel.send(f"⚠️ جميع أوامر البوت تعمل فقط في الروم المخصص: <#{allowed_channel_id}>")
            return

        period = "all"
        if len(parts) > 1:
            arg = parts[1].lower()
            if arg in ["day", "daily", "يومي", "اليوم"]:
                period = "daily"
            elif arg in ["week", "weekly", "اسبوعي", "أسبوعي", "الأسبوع"]:
                period = "weekly"
            elif arg in ["month", "monthly", "شهري", "الشهر"]:
                period = "monthly"
        ctx = await bot.get_context(message)
        await top_command(ctx, period)
        return

    # 3. احتساب خبرة الكتابة
    guild_id = message.guild.id
    user_id = message.author.id
    key = (guild_id, user_id)
    now = time.time()

    if key not in cooldowns or (now - cooldowns[key]) >= COOLDOWN_TIME:
        cooldowns[key] = now
        async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
            async with db.execute("SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cursor:
                row = await cursor.fetchone()

            if not row:
                xp, level = XP_PER_MESSAGE, 0
                await db.execute("INSERT INTO users (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)", (guild_id, user_id, xp, level))
            else:
                xp, level = row[0] + XP_PER_MESSAGE, row[1]
                old_level = level

                # حلقة while لحساب أي كمية ليفلات متراكمة
                while xp >= get_needed_xp(level):
                    xp -= get_needed_xp(level)
                    level += 1

                if level > old_level:
                    async with db.execute("SELECT level_channel_id FROM server_settings WHERE guild_id = ?", (guild_id,)) as cursor_lvl:
                        lvl_row = await cursor_lvl.fetchone()
                    
                    target_channel_id = lvl_row[0] if (lvl_row and lvl_row[0]) else None
                    level_channel = bot.get_channel(target_channel_id) if target_channel_id else message.channel
                    
                    if level_channel:
                        await level_channel.send(f"🎉 تهانينا {message.author.mention}! لقد ارتفعت إلى **Level {level}**!")
                    await check_role_rewards(message.author, level)

                await db.execute("UPDATE users SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", (xp, level, guild_id, user_id))
            await db.commit()
        
        await log_xp_gain(guild_id, user_id, XP_PER_MESSAGE)

    await bot.process_commands(message)

@tasks.loop(minutes=1)
async def voice_xp_loop():
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            real_members = [m for m in vc.members if not m.bot]
            if len(real_members) < 2:
                continue

            for member in real_members:
                if member.voice.self_deaf or member.voice.deaf:
                    continue
                
                async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
                    async with db.execute("SELECT voice_xp, voice_level FROM users WHERE guild_id = ? AND user_id = ?", (guild.id, member.id)) as cursor:
                        row = await cursor.fetchone()

                    if not row:
                        await db.execute("INSERT INTO users (guild_id, user_id, voice_xp, voice_level) VALUES (?, ?, ?, ?)", (guild.id, member.id, XP_PER_VOICE, 0))
                    else:
                        v_xp, v_level = (row[0] or 0) + XP_PER_VOICE, (row[1] or 0)
                        
                        # حلقة while لليفل الصوتي
                        while v_xp >= get_needed_xp(v_level):
                            v_xp -= get_needed_xp(v_level)
                            v_level += 1

                        await db.execute("UPDATE users SET voice_xp = ?, voice_level = ? WHERE guild_id = ? AND user_id = ?", (v_xp, v_level, guild.id, member.id))
                    await db.commit()

                await log_xp_gain(guild.id, member.id, XP_PER_VOICE)

# --------------------------------------------------
# 📖 أوامر البوت (Help)
# --------------------------------------------------
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 قائمة أوامر البوت",
        description="إليك جميع الأوامر المتاحة لاستخدامها داخل البوت:",
        color=discord.Color.from_rgb(88, 101, 242)
    )
    
    embed.add_field(
        name="👥 أوامر الأعضاء العامة",
        value=(
            "• `r` / `rank` : عرض بطاقة المستويات الخاصة بك.\n"
            "• `t` / `top` : عرض قائمة المتصدرين (شات وصوت).\n"
            "• `t day` / `week` / `month` : المتصدرين لفترة معينة.\n"
            "• `privacy` / `قفل` : إخفاء/إظهار ملفك الشخصي."
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ أوامر الإدارة الخاصة (المالك والآدمن)",
        value=(
            "• `!setlevel @user <level> [voice/صوتي]` : تحديد مستوى معين (الافتراضي: كتابي).\n"
            "• `!addxp @user <amount> [voice/صوتي]` : إضافة نقاط (الافتراضي: كتابي).\n"
            "• `!resetxp @user [كتابي/صوتي]` : تصفير نقاط ومستوى عضو (الافتراضي: تصفير الكل)."
        ),
        inline=False
    )
    
    embed.set_footer(text="💡 تنبيه: الأوامر الإدارية يمكن فقط للإدارة استخدامها.")
    await ctx.send(embed=embed)

async def rank_command(ctx, member: discord.Member = None):
    member = member or ctx.author
    guild_id = ctx.guild.id

    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        async with db.execute("SELECT is_private FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, member.id)) as cursor:
            priv_row = await cursor.fetchone()
            is_private = priv_row[0] if priv_row else 0

        is_admin = await check_admin_or_owner_user(ctx.author)
        if is_private and ctx.author.id != member.id and not is_admin:
            await ctx.send("🔒 هذا العضو قام بقفل ملفه الشخصي ولا يمكن رؤية مستواه إلا للإدارة والمالك!")
            return

        async with db.execute("SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, member.id)) as cursor:
            row_text = await cursor.fetchone()

        async with db.execute("SELECT voice_xp, voice_level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, member.id)) as cursor:
            row_voice = await cursor.fetchone()

        async with db.execute("SELECT user_id FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC", (guild_id,)) as cursor:
            all_text = await cursor.fetchall()
            text_rank = next((i for i, u in enumerate(all_text, 1) if u[0] == member.id), 1)

        async with db.execute("SELECT user_id FROM users WHERE guild_id = ? ORDER BY voice_level DESC, voice_xp DESC", (guild_id,)) as cursor:
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
    guild_id = ctx.guild.id
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        async with db.execute("SELECT is_private FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, ctx.author.id)) as cursor:
            row = await cursor.fetchone()

        current_status = row[0] if row else 0
        new_status = 1 if current_status == 0 else 0

        await db.execute("""
            INSERT INTO users (guild_id, user_id, is_private) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET is_private = excluded.is_private
        """, (guild_id, ctx.author.id, new_status))
        await db.commit()

    msg = "🔒 تم **قفل** بطاقتك التعرفية! لن يستطيع أحد رؤيتها غيرك والإدارة." if new_status else "🔓 تم **فتح** بطاقتك التعرفية للجميع!"
    await ctx.send(msg)

async def top_command(ctx, time_frame: str = "all"):
    guild_id = ctx.guild.id
    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        if time_frame == "all":
            embed = discord.Embed(title="🏆 قائمة المتصدرين (الكلي)", color=discord.Color.from_rgb(108, 63, 196))
            
            async with db.execute("SELECT user_id, level, xp FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 5", (guild_id,)) as cursor:
                text_rows = await cursor.fetchall()

            async with db.execute("SELECT user_id, voice_level, voice_xp FROM users WHERE guild_id = ? ORDER BY voice_level DESC, voice_xp DESC LIMIT 5", (guild_id,)) as cursor:
                voice_rows = await cursor.fetchall()

            text_desc = ""
            if text_rows:
                for idx, row in enumerate(text_rows, 1):
                    member = ctx.guild.get_member(row[0])
                    name = member.display_name if member else f"عضو مغادر ({row[0]})"
                    medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
                    text_desc += f"{medal} **{name}** — Level `{row[1]}` | `{format_number(row[2])} XP`\n"
            else:
                text_desc = "لا يوجد بيانات حتى الآن."

            voice_desc = ""
            if voice_rows:
                for idx, row in enumerate(voice_rows, 1):
                    member = ctx.guild.get_member(row[0])
                    name = member.display_name if member else f"عضو مغادر ({row[0]})"
                    medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
                    voice_desc += f"{medal} **{name}** — Voice Level `{row[1]}` | `{format_number(row[2])} XP`\n"
            else:
                voice_desc = "لا يوجد بيانات حتى الآن."

            embed.add_field(name="💬 المتصدرون في الشات (الكتابي)", value=text_desc, inline=False)
            embed.add_field(name="🎤 المتصدرون في الرومات (الصوتي)", value=voice_desc, inline=False)
            await ctx.send(embed=embed)
            return

        else:
            now = datetime.now(timezone.utc)
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
                WHERE guild_id = ? AND timestamp >= ? 
                GROUP BY user_id 
                ORDER BY total_xp DESC 
                LIMIT 10
            """, (guild_id, start_time)) as cursor:
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
        gained_xp = row[1]
        description += f"{medal} **{name}** — مكتسب: `{format_number(gained_xp)} XP`\n"

    embed.description = description
    await ctx.send(embed=embed)

# --------------------------------------------------
# 🛡️ أوامر الإدارة لتعديل النقاط
# --------------------------------------------------

@bot.command(name="setlevel")
async def set_level_cmd(ctx, member: discord.Member, new_level: int, xp_type: str = "text"):
    if not await check_admin_or_owner_user(ctx.author):
        await ctx.send("❌ **هذا الأمر مخصص لمالك السيرفر والإدارة فقط.**")
        return
        
    if new_level < 0:
        await ctx.send("⚠️ لا يمكن أن يكون المستوى أقل من صفر.")
        return
        
    guild_id = ctx.guild.id
    is_voice = xp_type.lower() in ["voice", "صوتي"]

    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        if is_voice:
            await db.execute("""
                INSERT INTO users (guild_id, user_id, voice_level, voice_xp) 
                VALUES (?, ?, ?, 0)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET voice_level = excluded.voice_level, voice_xp = 0
            """, (guild_id, member.id, new_level))
        else:
            await db.execute("""
                INSERT INTO users (guild_id, user_id, level, xp) 
                VALUES (?, ?, ?, 0)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET level = excluded.level, xp = 0
            """, (guild_id, member.id, new_level))
        await db.commit()
        
    if not is_voice:
        await check_role_rewards(member, new_level)

    msg_type = "الصوتي 🎤" if is_voice else "الكتابي 💬"
    await ctx.send(f"✅ تم تعديل مستوى {member.mention} **{msg_type}** إلى Level **{new_level}** بنجاح، وتم تحديث رتبته! 🎖️")

@bot.command(name="addxp")
async def add_xp_cmd(ctx, member: discord.Member, amount: int, xp_type: str = "text"):
    if not await check_admin_or_owner_user(ctx.author):
        await ctx.send("❌ **هذا الأمر مخصص لمالك السيرفر والإدارة فقط.**")
        return
        
    guild_id = ctx.guild.id
    is_voice = xp_type.lower() in ["voice", "صوتي"]

    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        if is_voice:
            async with db.execute("SELECT voice_xp, voice_level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, member.id)) as cursor:
                row = await cursor.fetchone()
                
            v_xp = (row[0] or 0) + amount if row else amount
            v_level = row[1] if row else 0
            
            # حلقة بينما تحسب أي كمية XP مضافة للمستوى الصوتي
            while v_xp >= get_needed_xp(v_level):
                v_xp -= get_needed_xp(v_level)
                v_level += 1
                
            if not row:
                await db.execute("INSERT INTO users (guild_id, user_id, voice_xp, voice_level) VALUES (?, ?, ?, ?)", (guild_id, member.id, v_xp, v_level))
            else:
                await db.execute("UPDATE users SET voice_xp = ?, voice_level = ? WHERE guild_id = ? AND user_id = ?", (v_xp, v_level, guild_id, member.id))
        else:
            async with db.execute("SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, member.id)) as cursor:
                row = await cursor.fetchone()
                
            xp = (row[0] or 0) + amount if row else amount
            level = row[1] if row else 0
            
            # حلقة بينما تحسب أي كمية XP مضافة للمستوى الكتابي
            while xp >= get_needed_xp(level):
                xp -= get_needed_xp(level)
                level += 1
                
            if not row:
                await db.execute("INSERT INTO users (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)", (guild_id, member.id, xp, level))
            else:
                await db.execute("UPDATE users SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", (xp, level, guild_id, member.id))
        await db.commit()
        
    # تحديث الرتب فوراً عند الزيادة
    if not is_voice:
        await check_role_rewards(member, level)
        
    msg_type = "الصوتي 🎤" if is_voice else "الكتابي 💬"
    current_level = v_level if is_voice else level
    await ctx.send(f"✅ تم إضافة **{amount} XP** {msg_type} لحساب {member.mention}. (وصل إلى Level **{current_level}**)")

@bot.command(name="resetxp")
async def reset_xp_cmd(ctx, member: discord.Member, xp_type: str = "all"):
    if not await check_admin_or_owner_user(ctx.author):
        await ctx.send("❌ **هذا الأمر مخصص لمالك السيرفر والإدارة فقط.**")
        return
        
    guild_id = ctx.guild.id
    is_voice = xp_type.lower() in ["voice", "صوتي"]
    is_text = xp_type.lower() in ["text", "كتابي"]

    async with aiosqlite.connect("leveling.db", timeout=20.0) as db:
        if is_voice:
            await db.execute("UPDATE users SET voice_xp = 0, voice_level = 0 WHERE guild_id = ? AND user_id = ?", (guild_id, member.id))
            msg_type = "الصوتية 🎤"
        elif is_text:
            await db.execute("UPDATE users SET xp = 0, level = 0 WHERE guild_id = ? AND user_id = ?", (guild_id, member.id))
            msg_type = "الكتابية 💬"
            await check_role_rewards(member, 0)
        else:
            await db.execute("UPDATE users SET xp = 0, level = 0, voice_xp = 0, voice_level = 0 WHERE guild_id = ? AND user_id = ?", (guild_id, member.id))
            msg_type = "الكلية (الكتابية والصوتية) 🔄"
            await check_role_rewards(member, 0)
            
        await db.commit()
        
    await ctx.send(f"✅ تم تصفير نقاط ومستويات {member.mention} **{msg_type}** بنجاح وتم تحديث الرتب.")

token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("❌ لم يتم العثور على التوكن في Environment Variables!")
