import traceback
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
import asyncio
import aiosqlite
import logging
import os
import utils
import discord_emoji
from dotenv import load_dotenv
import datetime
import sys
from typing import List, Set
import json

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
COGS = ['Cogs.ServerConfig.serverconfig', 'Cogs.LogMessages.logmessages', 'Cogs.AutoLockdown.autolockdown']

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


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: commands.CommandError):
    error = getattr(error, "original", error)
    if hasattr(ctx.command, 'name'):
        logger.error(f"'{type(error)}' exception occurred while executing command \'{ctx.command.name}\': {error}")
        formatted_exc = traceback.format_exception(error, value=error, tb=error.__traceback__)
        for l in ''.join(formatted_exc).split('\n'):
            logger.error(l)

@bot.event
async def on_ready():
    logging.info("CurfewBot online")
    await bot.update_guilds()

if bot.config['Bot']['jishaku']:
    bot.load_extension('jishaku')
    logging.info("Loaded jishaku")

try:
    bot.run(bot.config['Bot']['token'])
except discord.LoginFailure:
    logging.critical("Could not log in! Exiting. Check token in config?", exc_info=True)
    sys.exit()