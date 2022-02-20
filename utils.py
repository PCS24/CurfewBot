import os
from ruamel.yaml import YAML
yaml = YAML()
from typing import Sequence, List, Iterable, Set, Union, Optional
import discord
from discord.ext import commands
import copy
import aiosqlite
import logging
import datetime
import json
import traceback
import asyncio
from schema import Schema, And

DATABASE_PATH = "Database\main.db"
CALENDAR_PATH = "Database\calendar.db"

def getRootPath() -> Union[os.PathLike, str]:
    """
    Convenience function. Gets the root path of the bot.
    """
    return os.path.dirname(os.path.realpath(__file__))

os.chdir(getRootPath())

def genFromTemplate(template_path: os.PathLike, target_path: os.PathLike):
    """
    Detects if a file is missing, and generates it from its template if it is.
    """
    if not os.path.exists(target_path):
        with open(template_path, 'rb') as template_file:
            template = template_file.read()

        with open(target_path, 'wb') as f:
            f.write(template)

def updateConfig(template_path: os.PathLike, target_path: os.PathLike):
    """
    Detects if a config file is outdated by comparing it to its template, and then recursively updates it if it is.
    """
    template_data = yaml.load(open(template_path, 'r'))
    target_data = yaml.load(open(target_path, 'r'))
    if template_data['Metadata']['VERSION'] > target_data['Metadata']['VERSION']:
        # Template is newer than target, update target file
        new_data = copy.copy(template_data)

        target_data['Metadata']['VERSION'] = template_data['Metadata']['VERSION']

        def updateAttributes(thing1, thing2):
            for x in thing2.keys():
                if not hasattr(thing2[x], 'keys'):
                    thing1[x] = thing2[x]
                else:
                    updateAttributes(thing1[x], thing2[x])
            
            return thing1

        new_data = updateAttributes(new_data, target_data)
        yaml.dump(new_data, open(target_path, 'w'))

        return new_data

    else:
        # Target is not outdated, return existing data
        return target_data

def getConfig(template_path: os.PathLike, target_path: os.PathLike):
    """
    Convenience function. Generates the config (YAML) from template if it does not exist and updates it if it does exist and is outdated.
    """
    genFromTemplate(template_path, target_path)
    return updateConfig(template_path, target_path)

STATE_MAP = {
    True: 1,
    None: 0,
    False: -1
}

STATE_MAP_REVERSE = {y: x for x, y in STATE_MAP.items()}

class CurfewBot(commands.Bot):

    def __init__(self, config, *args, **kwargs):
        super(CurfewBot, self).__init__(*args, **kwargs)
        self.config = config
        self.logger = logging.getLogger('bot')
        genFromTemplate("Static/main.template_db", DATABASE_PATH)
        genFromTemplate("Static/calendar.template_db", CALENDAR_PATH)
        
    async def connect_db(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(DATABASE_PATH)

    async def connect_calendar(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(CALENDAR_PATH)

    async def _get_list_column(self, guild: discord.Guild, column: str, db: aiosqlite.Connection = None) -> List[int]:
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        try:
            items_raw = (await (await db.execute(f"SELECT \"{column}\" FROM GUILD_SETTINGS WHERE GUILD_ID=?", (guild.id,))).fetchone())[0]
            if items_raw == None:
                items = []
            else:
                items = items_raw.split(",")

            return items
        finally:
            if my_db:
                await db.close()

    async def _get_roles(self, guild: discord.Guild, column: str, db: aiosqlite.Connection = None) -> List[discord.Role]:
        return [guild.get_role(int(x)) for x in (await self._get_list_column(guild, column, db=db)) if x.isnumeric()]

    async def get_target_roles(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[discord.Role]:
        return await self._get_roles(guild, "TARGET_ROLES", db=db)

    async def get_ignored_roles(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[discord.Role]:
        return await self._get_roles(guild, "IGNORED_ROLES", db=db)

    async def get_ignored_channel_ids(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[int]:
        return [int(x) for x in (await self._get_list_column(guild, "IGNORED_CHANNELS", db=db)) if x.isnumeric()]

    async def get_ignored_channels(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[discord.abc.GuildChannel]:
        return [guild.get_channel(x) for x in await self.get_ignored_channel_ids(guild, db=db)]

    async def get_ignore_overwrites_preference(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> bool:
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        try:
            return bool((await (await db.execute("SELECT IGNORE_NEUTRAL_OVERWRITES FROM GUILD_SETTINGS WHERE GUILD_ID=?", (guild.id,))).fetchone())[0])
        finally:
            if my_db:
                await db.close()

    async def get_log_channel(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> Optional[discord.TextChannel]:
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        try:
            channel_id = (await (await db.execute("SELECT LOG_CHANNEL FROM GUILD_SETTINGS WHERE GUILD_ID=?", (guild.id,))).fetchone())[0]
        finally:
            if my_db:
                await db.close()
        
        channel = None
        if channel_id != None:
            channel = guild.get_channel(channel_id)
        return channel

    async def get_logs_enabled(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> bool:
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        try:
            enabled = (await (await db.execute("SELECT LOGS_ENABLED FROM GUILD_SETTINGS WHERE GUILD_ID=?", (guild.id,))).fetchone())[0]
        finally:
            if my_db:
                await db.close()
        
        return bool(enabled)

    def getColor(self, key: str) -> int:
        return int('0x' + self.config['Colors'][key], base=16)

    def getPlaceholder(self, key: str) -> str:
        return self.config['Bot']['placeholders'][key]

    
    async def update_guild_timestamp(self, guild: discord.Guild, column: str, db: aiosqlite.Connection = None):
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        try:
            # User-entered input should not be able to reach here in any form
            await db.execute(f"UPDATE STATE_INFO SET \"{column}\"=? WHERE GUILD_ID=?", (datetime.datetime.now().timestamp(), guild.id))
            await db.commit()
        finally:
            if my_db:
                await db.close()

    async def server_lockdown(self, guild: discord.Guild, target_roles: List[discord.Role], ignored_roles: List[discord.Role], whitelisted_channel_ids: List[int], ignore_neutral_overwrites: bool, db: aiosqlite.Connection = None, meta: dict = {}) -> dict:
        # Given the target server and the roles provided from the owner's config, lock down the server.
        # Input validation will be handled by the commands. Do not worry about it here, for the most part.

        self.logger.info(f"Locking down guild {guild.id}.")
        
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

                    # If the role is not in ignored_roles, set "View Channel" to False if not already disabled
                    if (r not in ignored_roles) and (r in target_roles or r == guild.default_role or (new_overwrites[r].view_channel != False and not ignore_neutral_overwrites) or (new_overwrites[r].view_channel == True and ignore_neutral_overwrites)):
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
            self.logger.error(f"Lockdown of guild {guild.id} (may have) failed. Traceback below.")
            self.logger.error(traceback.format_exc())
            raise
        else:
            success = True
            self.logger.info(f"Lockdown of guild {guild.id} was successful.")
        finally:
            # Broadcast event
            if success:
                self.dispatch('guild_lockdown', guild, report)

            # Return report dict
            report['meta']['timestamp'] = datetime.datetime.now().timestamp()
            report['meta']['guild_id'] = guild.id
            try:
                return report
            finally:
                # Update database
                my_db = db == None
                if my_db:
                    db = await self.connect_db()
                try:
                    await self.update_guild_timestamp(guild, 'LAST_LOCKDOWN', db=db)
                    await db.execute("UPDATE STATE_INFO SET LAST_LOCKDOWN_REPORT=? WHERE GUILD_ID=?", (json.dumps(report), guild.id))
                    await db.commit()
                finally:
                    if my_db:
                        await db.close()

    async def server_reopen(self, guild: discord.Guild, lockdown_report: dict, db: aiosqlite.Connection = None, meta: dict = {}) -> dict:
        self.logger.info(f"Reopening guild {guild.id}.")
        
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
            self.logger.error(f"Reopening of guild {guild.id} (may have) failed. Traceback below.")
            self.logger.error(traceback.format_exc())
            raise
        else:
            success = True
            self.logger.info(f"Reopening of guild {guild.id} was successful.")
        finally:
            # Finalize report
            report['missing_channels'] = list(set(report['missing_channels']))
            report['missing_roles'] = list(set(report['missing_roles']))
            report['meta']['timestamp'] = datetime.datetime.now().timestamp()
            report['meta']['guild_id'] = guild.id

            # Broadcast event
            if success:
                self.dispatch('guild_reopen', guild, report, lockdown_report)

            try:
                # Return report dict
                return report
            finally:
                # Update database
                my_db = db == None
                if my_db:
                    db = await self.connect_db()
                try:
                    await self.update_guild_timestamp(guild, 'LAST_REOPEN', db=db)
                finally:
                    if my_db:
                        await db.close()

    async def update_guilds(self, db: aiosqlite.Connection = None):
        my_db = db == None
        if my_db:
            db = await self.connect_db()
        
        try:
            TARGET_TABLES = ["STATE_INFO", "GUILD_SETTINGS"]
            db_guilds = {k: {x[0] for x in await db.execute_fetchall(f"SELECT GUILD_ID FROM {k}")} for k in TARGET_TABLES}
            for guild in self.guilds:
                for k in db_guilds.keys():
                    if guild.id not in db_guilds[k]:
                        await db.execute(f"INSERT INTO {k} (GUILD_ID) VALUES (?)", (guild.id,))
                        await db.commit()
        finally:
            if my_db:
                await db.close()

def getPrefix(bot: CurfewBot, message: discord.Message) -> str:
    """
    When a prefix-change command is implemented for external servers, this function will get the custom prefix
    """
    return bot.config['Bot']['default_prefix']


def check_embed(embed: discord.Embed) -> bool:
    """
    Evaluates all limits of embeds and returns whether or not they are satisfied.
    """
    return len(embed) <= 6000 and len(embed.fields) <= 25 and all(len(field.title) <= 256 and len(field.value) <= 1024 for field in embed.fields) and len(embed.title) <= 256 and len(embed.description) <= 4096 and len(embed.footer) <= 2048

def affected_channels_validator(d: dict) -> bool:
    return isinstance(d, dict) and all(isinstance(x, str) and x.isnumeric() and len(x) == 18 for x in d.keys()) and all(isinstance(x, list) and all(isinstance(y, list) and len(y) == 2 and isinstance(y[0], int) and isinstance(y[1], int) and len(str(y[0])) == 18 and y[1] in range(-1, 2) for y in x) for x in d.values())

def id_list_validator(d: dict) -> bool:
    return isinstance(d, list) and all(isinstance(x, int) and len(str(x)) == 18 for x in d)

LOCKDOWN_REPORT_SCHEMA = Schema({
    "affected_channels": And(affected_channels_validator, dict),
    "affected_roles": And(id_list_validator, list),
    "no_perms_channels": And(id_list_validator, list),
    "no_perms_roles": And(id_list_validator, list),
    "meta": dict
})