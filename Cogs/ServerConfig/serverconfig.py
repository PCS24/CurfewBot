import os
import sys
sys.path.append(os.getcwd())
import discord
from discord.ext import commands
from discord.commands.context import ApplicationContext
import utils
import logging
import aiosqlite

logger = logging.getLogger('cog-serverconfig')

NAME = "Config"
DESCRIPTION = "Commands for configuring the bot in your server."

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
                            roles = await ctx.bot.get_target_roles(ctx.guild)
                            embed = discord.Embed(
                                title="Role List",
                                description=('\n'.join([r.mention for r in roles]) if len(roles) > 0 else "*No roles found.*"),
                                color=ctx.bot.getColor('primary')
                            )
                            await ctx.respond(embed=embed, ephemeral=True)

                        @self.command(name="add", description="Adds a role to the list of roles that are affected by lockdowns and reopenings.")
                        async def add_role(ctx: ApplicationContext, role: discord.Role):
                            db = await ctx.bot.connect_db()
                            try:
                                roles = await ctx.bot.get_target_roles(ctx.guild, db=db)
                                if role in roles:
                                    await ctx.respond(f"{ctx.bot.getPlaceholder('error')} The role {role.mention} is already in the list.", ephemeral=True)
                                    return
                                roles.append(role)
                                await db.execute("UPDATE GUILD_SETTINGS SET TARGET_ROLES=? WHERE GUILD_ID=?", (','.join([str(r.id) for r in roles]), ctx.guild.id))
                                await db.commit()
                            finally:
                                await db.close()
                            await ctx.respond(f"Added role {role.mention} to the list.", ephemeral=True)

                        @self.command(name="remove", description="Removes a role from the list of roles that are affected by lockdowns and reopenings.")
                        async def remove_role(ctx: ApplicationContext, role: discord.Role):
                            db = await ctx.bot.connect_db()
                            try:
                                roles = await ctx.bot.get_target_roles(ctx.guild, db=db)
                                if role not in roles:
                                    await ctx.respond(f"{ctx.bot.getPlaceholder('error')} The role {role.mention} is not in the list.", ephemeral=True)
                                    return
                                roles.remove(role)
                                await db.execute("UPDATE GUILD_SETTINGS SET TARGET_ROLES=? WHERE GUILD_ID=?", (','.join([str(r.id) for r in roles]), ctx.guild.id))
                                await db.commit()
                            finally:
                                await db.close()
                            await ctx.respond(f"Removed role {role.mention} from the list.", ephemeral=True)

def setup(bot: utils.CurfewBot):
    bot.add_cog(ServerConfigCog(bot))