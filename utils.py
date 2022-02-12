import os
from ruamel.yaml import YAML
yaml = YAML()
from typing import Sequence, List, Iterable, Set, Union, Optional
import discord
from discord.ext import commands
import copy
import aiosqlite

DATABASE_PATH = "Database\main.db"

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

class CurfewBot(commands.Bot):

    def __init__(self, config, *args, **kwargs):
        super(CurfewBot, self).__init__(*args, **kwargs)
        self.config = config
        genFromTemplate("Static/main.template_db", DATABASE_PATH)
        
    async def connect_db(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(DATABASE_PATH)

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

    async def get_target_roles(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[discord.Role]:
        return [guild.get_role(int(x)) for x in (await self._get_list_column(guild, "TARGET_ROLES", db=db)) if x.isnumeric()]

    async def get_ignored_channels(self, guild: discord.Guild, db: aiosqlite.Connection = None) -> List[discord.abc.GuildChannel]:
        return [guild.get_channel(int(x)) for x in (await self._get_list_column(guild, "IGNORED_CHANNELS", db=db)) if x.isnumeric()]

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
