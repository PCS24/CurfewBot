import traceback
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
import asyncio
import logging
import os
import utils
import discord_emoji
from dotenv import load_dotenv
import datetime
import sys
from typing import List, Set

load_dotenv()

# Change working directory
ROOT_PATH = utils.getRootPath()
os.chdir(ROOT_PATH)

# Get config data
CONFIG = utils.getConfig('Static/config.template_yaml', 'Config/config.yaml')

# Configure logging
LOG_PATH = 'Logs/' + datetime.datetime.now().strftime("%m-%d-%Y_%H%M%S") + ".log"
log_level_switch = (
    {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
)
logging.basicConfig(level=log_level_switch[CONFIG['Logging']['logging_level'].upper()], format='%(asctime)s %(levelname)s %(name)s | %(message)s', datefmt=CONFIG['Logging']['date_format'])
logger = logging.getLogger()
fileHandler = logging.FileHandler(LOG_PATH)
fileHandler.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)s %(name)s | %(message)s', datefmt=CONFIG['Logging']['date_format']))
if CONFIG['Logging']['log_files']:
    logger.addHandler(fileHandler)
logging.info("Config loaded, logger started")
logging.info("Python " + sys.version.split(" ")[0])
logging.info("Discord.py version " + discord.__version__)

if CONFIG['Bot']['token'] == 'env':
    if not 'DISCORD_TOKEN' in os.environ.keys():
        logging.critical("Token set to 'env' in config but env variable 'DISCORD_TOKEN' was not found. Quitting.")
        sys.exit()
    else:
        CONFIG['Bot']['token'] = os.environ['DISCORD_TOKEN']

for p in CONFIG['Bot']['placeholders']:
    CONFIG['Bot']['placeholders'][p] = discord_emoji.to_unicode(CONFIG['Bot']['placeholders'][p])

# Create bot instance
bot = utils.CurfewBot(CONFIG, command_prefix=utils.getPrefix, intents=discord.Intents.all(), case_insensitive=True, debug_guilds=(CONFIG['Bot']['debug_guild_ids'] if CONFIG['Bot']['dev_mode'] else None))
#bot.remove_command('help') # Remove default help command

# Load cogs
# Add cog paths each time one is created
COGS = []

for cog in COGS:
    try:
        bot.load_extension(cog)
    except:
        logging.exception("Failed to load cog '" + cog + "'")
        raise
    else:
        logging.info("Loaded cog '" + cog + "'")

@bot.slash_command()
async def ping(ctx: ApplicationContext):
    """
    Returns the bot's API latency
    """
    await ctx.respond('Pong! `{0}`s'.format(round(bot.latency, 2)))

STATE_MAP = {
    True: 1,
    None: 0,
    False: -1
}

STATE_MAP_REVERSE = {y: x for x, y in STATE_MAP.items()}

async def server_lockdown(guild: discord.Guild, target_roles: List[discord.Role], whitelisted_channel_ids: List[int]) -> dict:
    # Given the target server and the roles provided from the owner's config, lock down the server.
    # Input validation will be handled by the commands. Do not worry about it here, for the most part.
    
    # Create report dict
    report = {
        'affected_channels': {}, # Each channel's ID will become a key (as a string) in this nested dict and the value will be a list of lists of the IDs of all affected roles and their previous permission states
        'affected_roles': [] # List of IDs of affected roles from target_roles plus the default role
    } # Since the default role has an ID, it will be included in the reports without special accommodation

    # Iterate over each unwhitelisted channel in the server:

    channels = [x for x in guild.channels if x.id not in whitelisted_channel_ids]
    for ch in channels:
        
        previous_state = None

        if ch.id not in report['affected_channels'].keys():
            report['affected_channels'][str(ch.id)] = []

        new_overwrites = ch.overwrites.copy()

        # If no overwrite present for the default role, create one
        if guild.default_role not in new_overwrites.keys():
            new_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            report['affected_channels'][str(ch.id)].append([guild.default_role.id, STATE_MAP[None]])

        # Iterate over each role in the channel's overwrites:
        for r in new_overwrites.keys():
            # Skip user-specific overwrites
            if not isinstance(r, discord.Role):
                continue

            # If the role is the guild's default role or it is in target_roles, set "View Channel" to False if not already disabled
            if (r in target_roles or r == guild.default_role) and (new_overwrites[r].view_channel != False):
                previous_state = STATE_MAP[new_overwrites[r].view_channel]
                new_overwrites[r].view_channel = False

                # Record all affected roles in the report dict
                report['affected_channels'][str(ch.id)].append([r.id, previous_state])

        if len(report['affected_channels'][str(ch.id)]) > 0:
            # Update channel permissions with new overwrites
            await ch.edit(overwrites=new_overwrites)

            # Delay to prevent ratelimiting
            await asyncio.sleep(len(channels) / 50)
        
        else:
            report['affected_channels'].pop(str(ch.id))

    # Iterate over the given roles + the server default role:
    roles = target_roles + [guild.default_role]
    for r in roles:
        # Set "View Channels" to False if not already disabled
        if r.permissions.view_channel != False:
            new_permissions = r.permissions
            new_permissions.update(view_channel=False)
            await r.edit(permissions=new_permissions)

            # Record all affected roles in the report dict
            report['affected_roles'].append(r.id)

            # Delay to prevent ratelimiting
            await asyncio.sleep(len(roles) / 50)

    # Return report dict
    return report
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    error = getattr(error, "original", error)
    if ctx.command != None:
        logging.exception(f"'{type(error)}' exception occurred while executing command \'{ctx.command.name}\': {error}")

@bot.event
async def on_ready():
    logging.info("CurfewBot online")

if bot.config['Bot']['jishaku']:
    bot.load_extension('jishaku')
    logging.info("Loaded jishaku")

try:
    bot.run(bot.config['Bot']['token'])
except discord.LoginFailure:
    logging.critical("Could not log in! Exiting. Check token in config?", exc_info=True)
    sys.exit()