
import os
import json
import random
import asyncio
import discord

from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands

# ==========================================
# DEV X BOT CONFIGURATION
# ==========================================

BOT_NAME = "DEV X BOT"
BOT_VERSION = "1.0"
BOT_EMOJI = "<:1000959271:1560245164843474944>"

TOKEN = os.getenv("TOKEN")
DATA_FILE = "giveaways.json"

# ==========================================
# BOT SETUP
# ==========================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

giveaways = {}
giveaway_tasks = {}
views_registered = False


# ==========================================
# DATA STORAGE
# ==========================================

def load_data():
    global giveaways

    if not os.path.exists(DATA_FILE):
        giveaways = {}
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            giveaways = json.load(file)
    except (json.JSONDecodeError, OSError):
        giveaways = {}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(giveaways, file, indent=4)


def current_timestamp():
    return int(datetime.now(timezone.utc).timestamp())


def get_color(value):
    if not value:
        return discord.Color.blurple()

    value = value.strip().replace("#", "")

    try:
        return discord.Color(int(value, 16))
    except ValueError:
        raise ValueError("Invalid HEX colour. Example: #5865F2")


def admin_only():
    return app_commands.checks.has_permissions(
        manage_guild=True
    )


async def get_text_channel(guild, channel_id):
    channel = guild.get_channel(int(channel_id))

    if channel is None:
        try:
            channel = await guild.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    if not isinstance(channel, discord.TextChannel):
        return None

    return channel


# ==========================================
# GIVEAWAY EMBEDS
# ==========================================

def make_giveaway_embed(data):
    embed = discord.Embed(
        title="GIVEAWAY",
        description=(
            f"**Prize:** {data['prize']}\n\n"
            f"**Winners:** {data['winners']}\n"
            f"**Ends:** <t:{data['end_time']}:R>\n\n"
            "Click the button below to enter!"
        ),
        color=discord.Color.red()
    )

    embed.add_field(
        name="Hosted By",
        value=f"<@{data['host_id']}>",
        inline=True
    )

    embed.add_field(
        name="Entries",
        value=str(len(data.get("entries", []))),
        inline=True
    )

    if data.get("required_role_id"):
        embed.add_field(
            name="Required Role",
            value=f"<@&{data['required_role_id']}>",
            inline=False
        )

    embed.set_footer(text="DEV X BOT • Giveaway")
    return embed


def make_ended_embed(data, winners):
    winner_text = (
        ", ".join(f"<@{user_id}>" for user_id in winners)
        if winners else "No valid entries"
    )

    embed = discord.Embed(
        title="GIVEAWAY ENDED",
        description=(
            f"**Prize:** {data['prize']}\n\n"
            f"**Winners:** {winner_text}"
        ),
        color=discord.Color.red()
    )

    embed.add_field(
        name="Total Entries",
        value=str(len(data.get("entries", []))),
        inline=True
    )

    embed.set_footer(text="DEV X BOT • Giveaway Ended")
    return embed


# ==========================================
# GIVEAWAY BUTTONS
# ==========================================

class GiveawayView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="ENTER GIVEAWAY",
        style=discord.ButtonStyle.primary,
        custom_id="devx:giveaway:enter"
    )
    async def enter(self, interaction, button):

        message_id = str(interaction.message.id)
        data = giveaways.get(message_id)

        if not data or not data.get("active"):
            await interaction.response.send_message(
                "This giveaway has ended.",
                ephemeral=True
            )
            return

        if current_timestamp() >= int(data["end_time"]):
            await interaction.response.send_message(
                "This giveaway has ended.",
                ephemeral=True
            )
            return

        role_id = data.get("required_role_id")

        if role_id and not any(
            role.id == int(role_id)
            for role in interaction.user.roles
        ):
            await interaction.response.send_message(
                "You do not have the required role to enter.",
                ephemeral=True
            )
            return

        user_id = str(interaction.user.id)

        if user_id in data.get("entries", []):
            await interaction.response.send_message(
                "You have already entered this giveaway.",
                ephemeral=True
            )
            return

        data.setdefault("entries", []).append(user_id)
        save_data()

        await interaction.response.send_message(
            "You have successfully entered the giveaway!",
            ephemeral=True
        )

        await update_giveaway_message(message_id)

    @discord.ui.button(
        label="LEAVE GIVEAWAY",
        style=discord.ButtonStyle.danger,
        custom_id="devx:giveaway:leave"
    )
    async def leave(self, interaction, button):

        message_id = str(interaction.message.id)
        data = giveaways.get(message_id)

        if not data or not data.get("active"):
            await interaction.response.send_message(
                "This giveaway has ended.",
                ephemeral=True
            )
            return

        user_id = str(interaction.user.id)

        if user_id not in data.get("entries", []):
            await interaction.response.send_message(
                "You are not entered in this giveaway.",
                ephemeral=True
            )
            return

        data["entries"].remove(user_id)
        save_data()

        await interaction.response.send_message(
            "You have left the giveaway.",
            ephemeral=True
        )

        await update_giveaway_message(message_id)

    @discord.ui.button(
        label="VIEW PARTICIPANTS",
        style=discord.ButtonStyle.secondary,
        custom_id="devx:giveaway:participants"
    )
    async def participants(self, interaction, button):

        message_id = str(interaction.message.id)
        data = giveaways.get(message_id)

        if not data:
            await interaction.response.send_message(
                "Giveaway data not found.",
                ephemeral=True
            )
            return

        entries = data.get("entries", [])

        if entries:
            description = "\n".join(
                f"<@{user_id}>" for user_id in entries[:40]
            )

            if len(entries) > 40:
                description += f"\nAnd {len(entries) - 40} more..."
        else:
            description = "No participants yet."

        embed = discord.Embed(
            title="GIVEAWAY PARTICIPANTS",
            description=description,
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="Total Participants",
            value=str(len(entries))
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# ==========================================
# UPDATE GIVEAWAY MESSAGE
# ==========================================

async def update_giveaway_message(message_id):
    data = giveaways.get(str(message_id))

    if not data:
        return

    guild = bot.get_guild(int(data["guild_id"]))

    if guild is None:
        return

    channel = await get_text_channel(
        guild,
        data["channel_id"]
    )

    if channel is None:
        return

    try:
        message = await channel.fetch_message(int(message_id))

        await message.edit(
            embed=make_giveaway_embed(data),
            view=GiveawayView()
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


# ==========================================
# FINISH GIVEAWAY
# ==========================================

async def finish_giveaway(message_id):
    message_id = str(message_id)
    data = giveaways.get(message_id)

    if not data or not data.get("active"):
        return False

    guild = bot.get_guild(int(data["guild_id"]))

    if guild is None:
        return False

    channel = await get_text_channel(
        guild,
        data["channel_id"]
    )

    if channel is None:
        return False

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False

    valid_entries = []

    for user_id in data.get("entries", []):
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue

        role_id = data.get("required_role_id")

        if role_id and not any(
            role.id == int(role_id)
            for role in member.roles
        ):
            continue

        valid_entries.append(str(user_id))

    winners = random.sample(
        valid_entries,
        min(int(data["winners"]), len(valid_entries))
    )

    data["active"] = False
    data["winner_ids"] = winners
    save_data()

    task = giveaway_tasks.get(message_id)

    if task and task is not asyncio.current_task():
        task.cancel()

    try:
        await message.edit(
            embed=make_ended_embed(data, winners),
            view=None
        )

        if winners:
            await channel.send(
                f"Congratulations {', '.join(f'<@{user_id}>' for user_id in winners)}! "
                f"You won **{data['prize']}**."
            )
        else:
            await channel.send(
                f"The giveaway for **{data['prize']}** ended without valid entries."
            )

    except discord.HTTPException:
        return False

    return True


# ==========================================
# GIVEAWAY TIMER
# ==========================================

async def giveaway_timer(message_id):
    try:
        while True:
            data = giveaways.get(str(message_id))

            if not data or not data.get("active"):
                return

            remaining = int(data["end_time"]) - current_timestamp()

            if remaining <= 0:
                await finish_giveaway(message_id)
                return

            await asyncio.sleep(min(remaining, 60))

    except asyncio.CancelledError:
        raise

    finally:
        if giveaway_tasks.get(str(message_id)) is asyncio.current_task():
            giveaway_tasks.pop(str(message_id), None)


def start_giveaway_timer(message_id):
    message_id = str(message_id)

    old_task = giveaway_tasks.get(message_id)

    if old_task and not old_task.done():
        return

    giveaway_tasks[message_id] = asyncio.create_task(
        giveaway_timer(message_id)
)


# ==========================================
# /GIVEAWAY_CREATE
# ==========================================

@bot.tree.command(
    name="giveaway_create",
    description="Create a new giveaway."
)
@admin_only()
@app_commands.describe(
    prize="What are you giving away?",
    duration_minutes="Giveaway duration in minutes.",
    winners="Number of winners.",
    channel="Channel where the giveaway will be posted.",
    required_role="Optional role required to enter."
)
async def giveaway_create(
    interaction: discord.Interaction,
    prize: str,
    duration_minutes: app_commands.Range[int, 1, 43200],
    winners: app_commands.Range[int, 1, 20],
    channel: discord.TextChannel,
    required_role: discord.Role = None
):

    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    end_time = current_timestamp() + (duration_minutes * 60)

    data = {
        "guild_id": interaction.guild.id,
        "channel_id": channel.id,
        "host_id": interaction.user.id,
        "prize": prize,
        "winners": winners,
        "end_time": end_time,
        "entries": [],
        "active": True,
        "required_role_id": required_role.id if required_role else None,
        "winner_ids": []
    }

    try:
        message = await channel.send(
            embed=make_giveaway_embed(data),
            view=GiveawayView()
        )
    except discord.HTTPException:
        await interaction.followup.send(
            "Could not create the giveaway. Check my channel permissions.",
            ephemeral=True
        )
        return

    giveaways[str(message.id)] = data
    save_data()

    start_giveaway_timer(message.id)

    await interaction.followup.send(
        f"Giveaway created successfully in {channel.mention}.\n"
        f"**Message ID:** `{message.id}`",
        ephemeral=True
    )


# ==========================================
# /GIVEAWAY_END
# ==========================================

@bot.tree.command(
    name="giveaway_end",
    description="End a giveaway using its message ID."
)
@admin_only()
@app_commands.describe(
    message_id="The giveaway message ID."
)
async def giveaway_end(
    interaction: discord.Interaction,
    message_id: str
):

    await interaction.response.defer(ephemeral=True)

    if not message_id.isdigit():
        await interaction.followup.send(
            "Please enter a valid message ID.",
            ephemeral=True
        )
        return

    data = giveaways.get(message_id)

    if not data:
        await interaction.followup.send(
            "Giveaway not found.",
            ephemeral=True
        )
        return

    if int(data["guild_id"]) != interaction.guild_id:
        await interaction.followup.send(
            "That giveaway does not belong to this server.",
            ephemeral=True
        )
        return

    if not data.get("active"):
        await interaction.followup.send(
            "This giveaway has already ended.",
            ephemeral=True
        )
        return

    success = await finish_giveaway(message_id)

    if success:
        await interaction.followup.send(
            "Giveaway ended successfully.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "Could not finish the giveaway. Check my permissions and try again.",
            ephemeral=True
        )



# ==========================================
# /EMBED_CREATE
# ==========================================

@bot.tree.command(
    name="embed_create",
    description="Create a custom embed."
)
@admin_only()
@app_commands.describe(
    title="Embed title.",
    description="Embed description.",
    color="HEX colour, for example #5865F2.",
    footer="Optional footer text.",
    author="Optional author text.",
    channel="Channel where the embed will be posted."
)
async def embed_create(
    interaction: discord.Interaction,
    title: str,
    description: str,
    color: str = "#5865F2",
    footer: str = None,
    author: str = None,
    channel: discord.TextChannel = None
):

    await interaction.response.defer(ephemeral=True)

    try:
        embed_color = get_color(color)
    except ValueError as error:
        await interaction.followup.send(
            str(error),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=embed_color
    )

    if footer:
        embed.set_footer(text=footer)

    if author:
        embed.set_author(name=author)

    target_channel = channel or interaction.channel

    if not isinstance(target_channel, discord.TextChannel):
        await interaction.followup.send(
            "Please choose a valid text channel.",
            ephemeral=True
        )
        return

    try:
        sent_message = await target_channel.send(embed=embed)
    except discord.HTTPException:
        await interaction.followup.send(
            "Could not send the embed. Check my permissions.",
            ephemeral=True
        )
        return

    await interaction.followup.send(
        f"Embed created successfully in {target_channel.mention}.\n"
        f"**Message ID:** `{sent_message.id}`",
        ephemeral=True
    )


# ==========================================
# /EMBED_EDIT
# ==========================================

@bot.tree.command(
    name="embed_edit",
    description="Edit an embed sent by DEV X BOT."
)
@admin_only()
@app_commands.describe(
    channel="Channel containing the embed.",
    message_id="Message ID of the embed.",
    title="New title. Leave blank to keep existing.",
    description="New description. Leave blank to keep existing.",
    color="New HEX colour. Leave blank to keep existing.",
    footer="New footer text. Leave blank to keep existing.",
    author="New author text. Leave blank to keep existing."
)
async def embed_edit(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message_id: str,
    title: str = None,
    description: str = None,
    color: str = None,
    footer: str = None,
    author: str = None
):

    await interaction.response.defer(ephemeral=True)

    if not message_id.isdigit():
        await interaction.followup.send(
            "Please enter a valid message ID.",
            ephemeral=True
        )
        return

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(
            "Message not found or I cannot access it.",
            ephemeral=True
        )
        return

    if message.author.id != bot.user.id:
        await interaction.followup.send(
            "I can only edit messages sent by DEV X BOT.",
            ephemeral=True
        )
        return

    if not message.embeds:
        await interaction.followup.send(
            "This message does not contain an embed.",
            ephemeral=True
        )
        return

    embed = discord.Embed.from_dict(
        message.embeds[0].to_dict()
    )

    if title is not None:
        embed.title = title or None

    if description is not None:
        embed.description = description or None

    if color is not None:
        try:
            embed.color = get_color(color)
        except ValueError as error:
            await interaction.followup.send(
                str(error),
                ephemeral=True
            )
            return

    if footer is not None:
        if footer:
            embed.set_footer(text=footer)
        else:
            embed.remove_footer()

    if author is not None:
        if author:
            embed.set_author(name=author)
        else:
            embed.remove_author()

    try:
        await message.edit(embed=embed)
    except discord.HTTPException:
        await interaction.followup.send(
            "Could not edit the embed. Check my permissions.",
            ephemeral=True
        )
        return

    await interaction.followup.send(
        "Embed updated successfully.",
        ephemeral=True
    )


# ==========================================
# /ABOUT
# ==========================================

@bot.tree.command(
    name="about",
    description="View information about DEV X BOT."
)
async def about(interaction: discord.Interaction):

    embed = discord.Embed(
        title=f"{BOT_EMOJI} About DEV X BOT",
        description=(
            f"**Bot Name:** {BOT_NAME}\n"
            f"**Version:** {BOT_VERSION}"
        ),
        color=discord.Color.blurple()
    )

    embed.timestamp = datetime.now(timezone.utc)
    embed.set_footer(text="DEV X BOT • About")

    await interaction.response.send_message(embed=embed)


# ==========================================
# ERROR HANDLING
# ==========================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(error, app_commands.MissingPermissions):
        message = "You need the **Manage Server** permission to use this command."
    else:
        print(f"Command error: {error}")
        message = "An unexpected error occurred. Please try again."

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


# ==========================================
# BOT STARTUP
# ==========================================

@bot.event
async def on_ready():
    global views_registered

    print(f"Logged in as {bot.user}")
    print(f"{BOT_NAME} is online.")

    if not views_registered:
        bot.add_view(GiveawayView())
        views_registered = True

    for message_id, data in giveaways.items():
        if data.get("active"):
            start_giveaway_timer(message_id)

    if not getattr(bot, "commands_synced", False):
        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} slash commands.")
            bot.commands_synced = True
        except discord.HTTPException as error:
            print(f"Command sync failed: {error}")


# ==========================================
# RUN BOT
# ==========================================

load_data()

if TOKEN == "YOUR_BOT_TOKEN" or not TOKEN:
    raise RuntimeError(
        "Please set your Discord bot token in the TOKEN environment variable."
    )

bot.run(TOKEN)
