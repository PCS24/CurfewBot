import os
import sys
sys.path.append(os.getcwd())
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
import utils
import logging
import aiosqlite
from typing import Coroutine, Any, Union, Callable
from io import BytesIO
import json
import traceback
from schema import SchemaError

logger = logging.getLogger('cog-admincommands')

NAME = "Admin Commands"
DESCRIPTION = "Commands for server owners and admins to manually operate the bot."

class AdminCommandsCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot

        def get_meta(ctx: ApplicationContext) -> dict:
            return {'auto': False, 'invoker_id': ctx.author.id}

        @commands.has_guild_permissions(administrator=True)
        @self.bot.slash_command(name="lockdown", description="Locks down the server and returns the report file.")
        async def lockdown_command(ctx: ApplicationContext):
            await ctx.defer()
            db = await ctx.bot.connect_db()
            try:
                logger.info(f"User {ctx.author.id} is locking down guild {ctx.guild.id}.")
                report = await ctx.bot.server_lockdown(ctx.guild, await ctx.bot.get_target_roles(ctx.guild, db=db), await ctx.bot.get_ignored_roles(ctx.guild, db=db), await ctx.bot.get_ignored_channel_ids(ctx.guild, db=db), await ctx.bot.get_ignore_overwrites_preference(ctx.guild, db=db), meta=get_meta(ctx), db=db)
            finally:
                await db.close()
            await ctx.respond("Successfully locked down the server.", file=discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename="report.json"))

        @commands.has_guild_permissions(administrator=True)
        @self.bot.slash_command(name="reopen", description="Reopens the server and returns the report file.")
        async def reopen_command(ctx: ApplicationContext, lockdown_report: discord.Attachment = None):
            await ctx.defer()

            if lockdown_report != None:
                # Validate lockdown report
                try:
                    assert lockdown_report.filename.endswith(".json")
                    assert lockdown_report.content_type == "application/json; charset=utf-8"
                    try:
                        input_json = json.loads(await lockdown_report.read())
                    except ValueError:
                        # JSON not readable
                        assert False
                    assert utils.LOCKDOWN_REPORT_SCHEMA.is_valid(input_json)
                except (AssertionError, SchemaError):
                    await ctx.respond(f"{ctx.bot.getPlaceholder('error')} Please make sure the file you uploaded is a valid lockdown report file. If this issue continues, contact the developer.")
                    return

            logger.info(f"User {ctx.author.id} is reopening guild {ctx.guild.id}.")
            db = await ctx.bot.connect_db()
            try:
                if lockdown_report == None:
                    input_json = (await (await db.execute("SELECT LAST_LOCKDOWN_REPORT FROM STATE_INFO WHERE GUILD_ID=?", (ctx.guild.id,))).fetchone())[0]
                    if input_json == None:
                        await ctx.respond(f"{ctx.bot.getPlaceholder('error')} There doesn't seem to be an existing lockdown report in my records. Please upload one if you have one.")
                        return
                    input_json = json.loads(input_json)
                report = await ctx.bot.server_reopen(ctx.guild, input_json, db=db, meta=get_meta(ctx))
            finally:
                await db.close()
            await ctx.respond("Successfully reopened the server.", file=discord.File(fp=BytesIO(json.dumps(report).encode('utf8')), filename="report.json"))


def setup(bot: utils.CurfewBot):
    bot.add_cog(AdminCommandsCog(bot))