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
COGS = ['Cogs.ServerConfig.serverconfig', 'Cogs.LogMessages.logmessages']

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

async def update_guild_timestamp(guild: discord.Guild, column: str, db: aiosqlite.Connection = None):
    my_db = db == None
    if my_db:
        db = await bot.connect_db()
    try:
        # User-entered input should not be able to reach here in any form
        await db.execute(f"UPDATE STATE_INFO SET \"{column}\"=? WHERE GUILD_ID=?", (datetime.datetime.now().timestamp(), guild.id))
        await db.commit()
    finally:
        if my_db:
            await db.close()

async def server_lockdown(guild: discord.Guild, target_roles: List[discord.Role], whitelisted_channel_ids: List[int], db: aiosqlite.Connection = None, meta: dict = {}) -> dict:
    # Given the target server and the roles provided from the owner's config, lock down the server.
    # Input validation will be handled by the commands. Do not worry about it here, for the most part.

    logger.info(f"Locking down guild {guild.id}.")
    
    # Create report dict
    report = {
        'affected_channels': {}, # Each channel's ID will become a key (as a string) in this nested dict and the value will be a list of lists of the IDs of all affected roles and their previous permission states
        'affected_roles': [], # List of IDs of affected roles from target_roles plus the default role
        'no_perms_channels': [], # List of IDs of channels the bot has no permission to edit
        'no_perms_roles': [], # List of IDs of roles the bot has no permission to edit
        'meta': {'provided': meta}
    } # Since the default role has an ID, it will be included in the reports without special accommodation

    success = False
    try:
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
                try:
                    await ch.edit(overwrites=new_overwrites)
                except discord.errors.Forbidden:
                    # Record error in report, continue to next iteration
                    report['no_perms_channels'].append(ch.id)
                    continue

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
                try:
                    await r.edit(permissions=new_permissions)
                except discord.errors.Forbidden:
                    # Record error in report, continue to next iteration
                    report['no_perms_roles'].append(r.id)
                    continue

                # Record all affected roles in the report dict
                report['affected_roles'].append(r.id)

                # Delay to prevent ratelimiting
                await asyncio.sleep(len(roles) / 50)
    except:
        logger.info(f"Lockdown of guild {guild.id} (may have) failed.")
        raise
    else:
        success = True
        logger.info(f"Lockdown of guild {guild.id} was successful.")
    finally:
        # Broadcast event
        if success:
            bot.dispatch('guild_lockdown', guild, report)

        # Return report dict
        report['meta']['timestamp'] = datetime.datetime.now().timestamp()
        report['meta']['guild_id'] = guild.id
        try:
            return report
        finally:
            # Update database
            my_db = db == None
            if my_db:
                db = await bot.connect_db()
            try:
                await update_guild_timestamp(guild, 'LAST_LOCKDOWN', db=db)
                await db.execute("UPDATE STATE_INFO SET LAST_LOCKDOWN_REPORT=? WHERE GUILD_ID=?", (json.dumps(report), guild.id))
                await db.commit()
            finally:
                if my_db:
                    await db.close()

async def server_reopen(guild: discord.Guild, lockdown_report: dict, db: aiosqlite.Connection = None, meta: dict = {}) -> dict:
    logger.info(f"Reopening guild {guild.id}.")
    
    # Create report dict
    report = {
        "missing_channels": [],
        "missing_roles": [],
        "missing_overwrites": {}, # Keys, stringified channel IDs. Values, lists of role IDs.
        "no_perms_roles": [],
        "no_perms_channels": [],
        "meta": {'provided': meta}
    }
    
    success = False

    try:
        # Iterate over each affected channel in lockdown_report:
        for k in lockdown_report['affected_channels'].keys():
            # Get the channel from the channel ID
            channel = guild.get_channel(int(k))
            # If channel not found, store the problem in the report and continue to next iteration
            if channel == None:
                report['missing_channels'].append(int(k))
                continue
            
            new_overwrites = channel.overwrites.copy()
            # Iterate over each list in the list for the channel:
            for ov in lockdown_report['affected_channels'][k]:
                # Get the role ID from the first element and try to get the role
                role = guild.get_role(ov[0])
                # If role not found, store the problem in the report and continue to next iteration
                if role == None:
                    report['missing_roles'].append(ov[0])
                    continue
                # If role is no longer in the overwrites for the channel, store the problem in the report and continue to next iteration
                if role not in new_overwrites.keys():
                    if k not in report['missing_overwrites'].keys():
                        report['missing_overwrites'][k] = []
                    if ov[0] not in report['missing_overwrites'][k]:
                        report['missing_overwrites'][k].append(ov[0])
                    continue

                # Edit the overwrite for the role in that channel to match the original permission state specified in lockdown_report
                previous_state = new_overwrites[role].view_channel
                new_overwrites[role].view_channel = STATE_MAP_REVERSE[ov[1]]
                
                # Take note of the change in the report and include the original state from before reopening
                #TODO
            
            # Update channel
            try:
                await channel.edit(overwrites=new_overwrites)
            except discord.errors.Forbidden:
                # Record error in report, continue to next iteration
                report['no_perms_channels'].append(channel.id)
                continue

            # Delay to prevent ratelimiting
            await asyncio.sleep(len(lockdown_report['affected_channels']) / 50)
            
            # If the channel was affected, take note of the change in the report
            #TODO

        # Iterate over each affected role in lockdown_report:
        for r_id in lockdown_report['affected_roles']:
            # Get the role from the role ID
            role = guild.get_role(r_id)
            # If role not found, store the problem in the report and continue to next iteration
            if role == None:
                report['missing_roles'].append(r_id)
                continue

            # Edit the role so that "View channels" permission is enabled (lockdown_report would only have it stored if it was previously enabled)
            new_permissions = role.permissions
            new_permissions.update(view_channel=True)
            try:
                await role.edit(permissions=new_permissions)
            except discord.errors.Forbidden:
                # Record error in report, continue to next iteration
                report['no_perms_roles'].append(role.id)
                continue
            # Take note of the change in the report
            #TODO

            # Delay to prevent ratelimiting
            await asyncio.sleep(len(lockdown_report['affected_roles']) / 50)
    except:
        logger.info(f"Reopening of guild {guild.id} (may have) failed.")
        raise
    else:
        success = True
        logger.info(f"Reopening of guild {guild.id} was successful.")
    finally:
        # Finalize report
        report['missing_channels'] = list(set(report['missing_channels']))
        report['missing_roles'] = list(set(report['missing_roles']))
        report['meta']['timestamp'] = datetime.datetime.now().timestamp()
        report['meta']['guild_id'] = guild.id

        # Broadcast event
        if success:
            bot.dispatch('guild_reopen', guild, report, lockdown_report)

        try:
            # Return report dict
            return report
        finally:
            # Update database
            my_db = db == None
            if my_db:
                db = await bot.connect_db()
            try:
                await update_guild_timestamp(guild, 'LAST_REOPEN', db=db)
            finally:
                if my_db:
                    await db.close()

async def update_guilds(db: aiosqlite.Connection = None):
    my_db = db == None
    if my_db:
        db = await bot.connect_db()
    
    try:
        TARGET_TABLES = ["STATE_INFO", "GUILD_SETTINGS"]
        db_guilds = {k: {x[0] for x in await db.execute_fetchall(f"SELECT GUILD_ID FROM {k}")} for k in TARGET_TABLES}
        for guild in bot.guilds:
            for k in db_guilds.keys():
                if guild.id not in db_guilds[k]:
                    await db.execute(f"INSERT INTO {k} (GUILD_ID) VALUES (?)", (guild.id,))
                    await db.commit()
    finally:
        if my_db:
            await db.close()


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    error = getattr(error, "original", error)
    if ctx.command != None:
        logging.exception(f"'{type(error)}' exception occurred while executing command \'{ctx.command.name}\': {error}")

@bot.event
async def on_ready():
    logging.info("CurfewBot online")
    await update_guilds()

if bot.config['Bot']['jishaku']:
    bot.load_extension('jishaku')
    logging.info("Loaded jishaku")

try:
    bot.run(bot.config['Bot']['token'])
except discord.LoginFailure:
    logging.critical("Could not log in! Exiting. Check token in config?", exc_info=True)
    sys.exit()