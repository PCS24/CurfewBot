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
        
        embed = discord.Embed(
            title="Server Locked Down",
            color=self.bot.getColor('secondary')
        )

        if len(report['affected_roles']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('success')} Affected Roles", value=", ".join([guild.get_role(r).mention for r in report['affected_roles']]), inline=False)
        if len(report['affected_channels']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('success')} Affected Channels", value=", ".join([guild.get_channel(int(c)).mention for c in report['affected_channels'].keys()]), inline=False)
        
        if len(report['no_perms_roles']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Untouchable Roles", value=", ".join([guild.get_role(r).mention for r in report['no_perms_roles']]), inline=False)
        if len(report['no_perms_channels']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Untouchable Channels", value=", ".join([guild.get_channel(c).mention for c in report['no_perms_channels']]), inline=False)
        
        # Verify that the embed can be sent; if not, send the report without the embed
        embed_check = utils.check_embed(embed)

        await log_channel.send(
            ("**Server Locked Down**\n*The neat-looking embed report was too long to be sent, but all the data is still attached below if you need it.*" if not embed_check else None),
            embed=(embed if embed_check else None),
            files=[discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename='lockdown.json')]
        )

    @commands.Cog.listener()
    async def on_guild_reopen(self, guild: discord.Guild, report: dict, lockdown_report: dict):
        log_channel = await self.bot.get_log_channel(guild)
        if log_channel == None:
            return
        
        embed = discord.Embed(
            title="Server Reopened",
            color=self.bot.getColor('secondary')
        )

        if len(report['missing_roles']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Missing Roles", value=", ".join([f"Role `{r}`" for r in report['missing_roles']]), inline=False)
        if len(report['missing_channels']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Missing Channels", value=", ".join([f"Channel `{c}`" for c in report['missing_channels']]), inline=False)

        if len(report['no_perms_roles']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Untouchable Roles", value=", ".join([guild.get_role(r).mention for r in report['no_perms_roles']]), inline=False)
        if len(report['no_perms_channels']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Untouchable Channels", value=", ".join([guild.get_channel(c).mention for c in report['no_perms_channels']]), inline=False)

        if len(report['missing_overwrites']) > 0:
            embed.add_field(name=f"{self.bot.getPlaceholder('warning')} Missing Overwrites", value="\n".join([f"{guild.get_channel(int(k)).mention}: " + ", ".join([guild.get_role(o).mention for o in report['missing_overwrites'][k] if o not in report['missing_roles']]) for k in report['missing_overwrites'].keys()]), inline=False)

        # Verify that the embed can be sent; if not, send the report without the embed
        embed_check = utils.check_embed(embed)

        await log_channel.send(
            ("**Server Reopened**\n*The neat-looking embed report was too long to be sent, but all the data is still attached below if you need it.*" if not embed_check else None),
            embed=(embed if embed_check else None),
            files=[discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename='reopening.json'), discord.File(fp=BytesIO(json.dumps(lockdown_report).encode('utf8')), filename='lockdown.json')]
        )

def setup(bot: utils.CurfewBot):
    bot.add_cog(LogMessagesCog(bot))