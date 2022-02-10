import os
import sys
sys.path.append(os.getcwd())
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
import utils
import logging
import aiosqlite
import json
from io import BytesIO

logger = logging.getLogger('cog-logmessages')

NAME = "Logging"
DESCRIPTION = "Handles logs."

class LogMessagesCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_lockdown(self, guild: discord.Guild, report: dict):
        log_channel = await self.bot.get_log_channel(guild)
        if log_channel == None:
            return
        
        await log_channel.send(
            "**Server Locked Down**", 
            files=[discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename='lockdown.json')]
        )

    @commands.Cog.listener()
    async def on_guild_reopen(self, guild: discord.Guild, report: dict, lockdown_report: dict):
        log_channel = await self.bot.get_log_channel(guild)
        if log_channel == None:
            return
        
        await log_channel.send(
            "**Server Reopened**", 
            files=[discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename='reopening.json'), discord.File(fp=BytesIO(json.dumps(lockdown_report).encode('utf8')), filename='lockdown.json')]
        )

def setup(bot: utils.CurfewBot):
    bot.add_cog(LogMessagesCog(bot))