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

logger = logging.getLogger('cog-serverconfig')

NAME = "Config"
DESCRIPTION = "Commands for configuring the bot in your server."

# Functions that are reused in both RolesGroup and ChannelsGroup
async def list_objects(ctx: ApplicationContext, name: str, fetch_func: Callable, color_key: str = 'primary'):
    objects = await fetch_func(ctx.guild)
    embed = discord.Embed(
        title=(' '.join([n.capitalize() for n in name.split(' ')]) + " List"),
        description=('\n'.join([o.mention for o in objects]) if len(objects) > 0 else f"*No {name}s found.*"),
        color=ctx.bot.getColor(color_key)
    )
    await ctx.respond(embed=embed, ephemeral=True)

async def edit_object_list(ctx: ApplicationContext, name: str, fetch_func: Callable, appending: bool, value: Union[discord.Role, discord.abc.GuildChannel], column: str):
    db = await ctx.bot.connect_db()
    try:
        objects = await fetch_func(ctx.guild, db=db)
        if ((value in objects) and appending) or ((value not in objects) and not appending):
            await ctx.respond(f"{ctx.bot.getPlaceholder('error')} The {name} {value.mention} is {'already' if appending else 'not'} in the list.", ephemeral=True)
            return
        (objects.append if appending else objects.remove)(value)
        await db.execute(f"UPDATE GUILD_SETTINGS SET \"{column}\"=? WHERE GUILD_ID=?", (','.join([str(o.id) for o in objects]), ctx.guild.id))
        await db.commit()
    finally:
        await db.close()
    await ctx.respond(f"{'Added' if appending else 'Removed'} {name} {value.mention} {'to' if appending else 'from'} the list.", ephemeral=True)

async def toggle_column(ctx: ApplicationContext, column: str) -> bool:
    db = await ctx.bot.connect_db()
    try:
        current_state = (await (await db.execute(f"SELECT \"{column}\" FROM GUILD_SETTINGS WHERE GUILD_ID=?", (ctx.guild.id,))).fetchone())[0]
        await db.execute(f"UPDATE GUILD_SETTINGS SET \"{column}\"=? WHERE GUILD_ID=?", (0 if current_state else 1, ctx.guild.id))
        await db.commit()
    finally:
        await db.close()
    return not current_state

class ServerConfigCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot

        @commands.guild_only()
        @commands.has_guild_permissions(administrator=True)
        @self.bot.slash_group(name=NAME.lower().replace(" ", ""), description=DESCRIPTION)
        class ServerConfigGroup(discord.SlashCommandGroup):
            def __init__(self, *args, **kwargs):
                super(type(self), self).__init__(*args, **kwargs)
                
                @self.subgroup("roles", "Manage the list of roles that are affected by lockdowns and reopenings.")
                class RolesGroup(discord.SlashCommandGroup):
                    def __init__(self, *args, **kwargs):
                        super(type(self), self).__init__(*args, **kwargs)

                        @self.command(name="list", description="Lists all roles that are affected by lockdowns and reopenings.")
                        async def list_roles(ctx: ApplicationContext):
                            await list_objects(ctx, 'role', ctx.bot.get_target_roles)

                        @self.command(name="add", description="Adds a role to the list of roles that are affected by lockdowns and reopenings.")
                        async def add_role(ctx: ApplicationContext, role: discord.Role):
                            await edit_object_list(ctx, 'role', ctx.bot.get_target_roles, True, role, "TARGET_ROLES")

                        @self.command(name="remove", description="Removes a role from the list of roles that are affected by lockdowns and reopenings.")
                        async def remove_role(ctx: ApplicationContext, role: discord.Role):
                            await edit_object_list(ctx, 'role', ctx.bot.get_target_roles, False, role, "TARGET_ROLES")

                @self.subgroup("channels", "Manage the list of channels that are ignored by lockdowns and reopenings.")
                class ChannelsGroup(discord.SlashCommandGroup):
                    def __init__(self, *args, **kwargs):
                        super(type(self), self).__init__(*args, **kwargs)

                        channel_option = discord.Option((discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.StageChannel), "The channel/category. Category permissions may sync to ignored channels if already synced.")

                        @self.command(name="list", description="Lists all ignored channels.")
                        async def list_roles(ctx: ApplicationContext):
                            await list_objects(ctx, 'ignored channel', ctx.bot.get_ignored_channels)

                        @self.command(name="ignore", description="Adds a channel to the list of ignored channels.")
                        async def ignore_channel(ctx: ApplicationContext, channel: channel_option):
                            await edit_object_list(ctx, 'channel', ctx.bot.get_ignored_channels, True, channel, "IGNORED_CHANNELS")

                        @self.command(name="unignore", description="Removes a channel from the list of ignored channels.")
                        async def unignore_channel(ctx: ApplicationContext, channel: channel_option):
                            await edit_object_list(ctx, 'channel', ctx.bot.get_ignored_channels, False, channel, "IGNORED_CHANNELS")

                @self.subgroup("logs", "Manage logging features. Enabling logs is strongly recommended.")
                class LogsGroup(discord.SlashCommandGroup):
                    def __init__(self, *args, **kwargs):
                        super(type(self), self).__init__(*args, **kwargs)

                        @self.command(name="setchannel", description="Sets the channel where logs will be sent.")
                        async def set_log_channel(ctx: ApplicationContext, channel: discord.TextChannel):
                            channel_perms: discord.Permissions = channel.permissions_for(ctx.guild.me)
                            if not (channel_perms.view_channel and channel_perms.send_messages and channel_perms.use_external_emojis and channel_perms.embed_links and channel_perms.attach_files):
                                await ctx.respond(f"{ctx.bot.getPlaceholder('error')} Please make sure I have all of the following permissions in {channel.mention} first: `View Channel`, `Send Messages`, `Embed Links`, `Attach Files`, and `Use External Emojis`.", ephemeral=True)
                                return
                            db = await ctx.bot.connect_db()
                            try:
                                await db.execute("UPDATE GUILD_SETTINGS SET LOG_CHANNEL=? WHERE GUILD_ID=?", (channel.id, ctx.guild.id))
                                await db.commit()
                            finally:
                                await db.close()
                            await ctx.respond(f"{ctx.bot.getPlaceholder('success')} Log channel has been set to {channel.mention}.", ephemeral=True)

                        @self.command(name="toggle", description="Toggles logging.")
                        async def toggle_logs(ctx: ApplicationContext):
                            new_state = await toggle_column(ctx, "LOGS_ENABLED")
                            await ctx.respond(f"{ctx.bot.getPlaceholder('success')} Logging has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)

                        @self.command(name="get", description="Allows you to view the current logging settings.")
                        async def get_logging_settings(ctx: ApplicationContext):
                            db = await ctx.bot.connect_db()
                            try:
                                enabled, channel_id = (await (await db.execute("SELECT LOGS_ENABLED, LOG_CHANNEL FROM GUILD_SETTINGS WHERE GUILD_ID=?", (ctx.guild.id,))).fetchone())
                            finally:
                                await db.close()
                            await ctx.respond(f"Logging is currently **{'enabled' if enabled else 'disabled'}**{f' in channel <#{channel_id}>' if channel_id != None else ''}.", ephemeral=True)

                @self.subgroup("calendar", "Manage automatic lockdowns/reopenings based on the bot's synchronized calendar.")
                class CalendarGroup(discord.SlashCommandGroup):
                    def __init__(self, *args, **kwargs):
                        super(type(self), self).__init__(*args, **kwargs)

                        @self.command(name="toggle", description="Toggles whether the bot should automatically lockdown/reopen using the synced calendar.")
                        async def toggle_sync(ctx: ApplicationContext):
                            db = await ctx.bot.connect_db()
                            try:
                                current_state = (await (await db.execute("SELECT USE_CALENDAR FROM GUILD_SETTINGS WHERE GUILD_ID=?", (ctx.guild.id,))).fetchone())[0]
                                await db.execute("UPDATE GUILD_SETTINGS SET USE_CALENDAR=? WHERE GUILD_ID=?", (0 if current_state else 1, ctx.guild.id))
                                await db.commit()
                            finally:
                                await db.close()
                            await ctx.respond(f"{ctx.bot.getPlaceholder('success')} Calendar scheduling has been **{'disabled' if current_state else 'enabled'}**.", ephemeral=True)

                        @self.command(name="get", description="Allows you to view the current calendar settings.")
                        async def get_calendar_settings(ctx: ApplicationContext):
                            db = await ctx.bot.connect_db()
                            try:
                                enabled = (await ((await db.execute("SELECT USE_CALENDAR FROM GUILD_SETTINGS WHERE GUILD_ID=?", (ctx.guild.id,))).fetchone()))[0]
                            finally:
                                await db.close()
                            await ctx.respond(f"Automatic lockdowns and reopenings using the synchronized calendar are currently **{'enabled' if enabled else 'disabled'}**.", ephemeral=True)

def setup(bot: utils.CurfewBot):
    bot.add_cog(ServerConfigCog(bot))