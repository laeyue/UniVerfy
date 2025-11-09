import os
import re
import asyncio
import random
from email.message import EmailMessage  # <-- ADD THIS IMPORT

import discord
from discord import app_commands
from discord.ext import commands

import aiosmtplib
import redis.asyncio as aioredis


# --- THESE ARE NOW PULLED FROM YOUR .env FILE ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM")
# -------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/2")
ROLE_NAME = os.getenv("ROLE_NAME", "Verified")
VERIFICATION_TTL = int(os.getenv("VERIFICATION_TTL", "120"))  # 2 minutes default

# Email regex for *.edu.ph
EDUPH_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)*edu\.ph$", re.IGNORECASE)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

redis = aioredis.from_url(REDIS_URL, decode_responses=True)

def gen_code():
    return f"{random.randint(100000, 999999)}"

#
# --- THIS IS THE ONLY MODIFIED FUNCTION ---
#
async def send_verification_email(to_email: str, code: str):
    # Using EmailMessage is more robust than a raw string
    msg = EmailMessage()
    msg["Subject"] = "Discord verification code"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    
    body = f"""
    Your verification code is: {code}

    This code will expire in {VERIFICATION_TTL} seconds.
    """
    msg.set_content(body)

    # aiosmtplib.send handles the EmailMessage object correctly
    await aiosmtplib.send(
        msg,  # Pass the message object
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USER,
        password=SMTP_PASS,
        start_tls=True,
    )
#
# --- NO OTHER CODE WAS CHANGED ---
#

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("Failed to sync commands:", e)

@tree.command(name="verify", description="Start email verification with your university email")
@app_commands.describe(email="Your university email (must end with .edu.ph)")
async def verify(interaction: discord.Interaction, email: str):
    await interaction.response.defer(ephemeral=True)

    if not EDUPH_REGEX.match(email):
        await interaction.followup.send("That email is not an @*.edu.ph address. Use university email only.", ephemeral=True)
        return

    code = gen_code()
    key = f"verify:{interaction.user.id}"

    await redis.hset(key, mapping={"email": email, "code": code})
    await redis.expire(key, VERIFICATION_TTL)

    try:
        await send_verification_email(email, code)
    except Exception as e:
        await interaction.followup.send(f"Failed to send email: {e}", ephemeral=True)
        await redis.delete(key)
        return

    await interaction.followup.send(f"Code sent to `{email}`. Use `/code <6digits>` within {VERIFICATION_TTL} seconds.", ephemeral=True)

@tree.command(name="code", description="Submit the verification code you received by email")
@app_commands.describe(code="6-digit verification code")
async def submit_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(ephemeral=True)
    key = f"verify:{interaction.user.id}"
    data = await redis.hgetall(key)
    if not data:
        await interaction.followup.send("No verification pending or it expired. Start again with `/verify`.", ephemeral=True)
        return

    expected = data.get("code")
    email = data.get("email")
    if code.strip() != expected:
        await interaction.followup.send("Wrong code.", ephemeral=True)
        return

    guild = interaction.guild
    if guild is None:
        await interaction.followup.send("Use this command inside the server.", ephemeral=True)
        return

    member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except:
            await interaction.followup.send("Member not found.", ephemeral=True)
            return

    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        await interaction.followup.send(f"Role `{ROLE_NAME}` not found. Admin must create it.", ephemeral=True)
        return

    try:
        await member.add_roles(role, reason=f"Verified via {email}")
    except Exception as e:
        await interaction.followup.send(f"Cannot add role: {e}", ephemeral=True)
        return

    await redis.delete(key)
    await interaction.followup.send(f"Verified ✅ role `{ROLE_NAME}` granted.", ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN not set.")
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM]):
        print("WARNING: SMTP variables not fully set. Email sending will fail.")
        
    bot.run(DISCORD_TOKEN)