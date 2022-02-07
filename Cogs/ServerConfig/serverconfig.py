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

class ServerConfigCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot

        @commands.guild_only()
        @commands.has_guild_permissions(administrator=True)
        @self.bot.slash_group(name=NAME.lower(), description=DESCRIPTION)
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


def setup(bot: utils.CurfewBot):
    bot.add_cog(ServerConfigCog(bot))