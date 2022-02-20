import os
import sys
sys.path.append(os.getcwd())
import discord
from discord.ext import commands, tasks
from discord.commands.context import ApplicationContext
import utils
from utils import CALENDAR_PATH
import logging
import aiosqlite
import json
import datetime
import asyncio

logger = logging.getLogger('cog-autolockdown')

NAME = "Automatic Lockdown System"
DESCRIPTION = "Automatically locks down and reopens servers on a set schedule."

class AutoLockdownCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot
        self.calendar_poll.start()

    @tasks.loop(seconds=600)
    async def calendar_poll(self):
        # Get the oldest uncompleted scheduled task in the calendar whose SCHEDULED_TIMESTAMP is in the past
        # Perform the task and update the calendar as needed
        await self.bot.wait_until_ready()
        cal = await self.bot.connect_calendar()
        db = await self.bot.connect_db()
        try:
            action_info = await (await cal.execute("SELECT ACTION, SCHEDULED_TIMESTAMP FROM CALENDAR WHERE SCHEDULED_TIMESTAMP < ? AND COMPLETED=0 ORDER BY SCHEDULED_TIMESTAMP DESC LIMIT 1", (datetime.datetime.now().timestamp(),))).fetchone()
            if action_info == None:
                return
            
            report_meta = {'auto': True, 'scheduled_timestamp': action_info[1]}
            guild_rows = await db.execute_fetchall("SELECT * FROM STATE_INFO WHERE GUILD_ID IN (SELECT GUILD_ID FROM GUILD_SETTINGS WHERE USE_CALENDAR=1)")
            for guild_row in guild_rows:
                guild = self.bot.get_guild(guild_row[0])
                if guild == None:
                    continue
                
                if action_info[0] == 'LOCKDOWN':
                    # Check if server is already locked down
                    if guild_row[1] > guild_row[2]:
                        continue
                    
                    # Lock down server
                    logger.info(f"Automatically locking down guild {guild_row[0]}.")
                    await self.bot.server_lockdown(guild, await self.bot.get_target_roles(guild, db=db), await self.bot.get_ignored_roles(guild, db=db), await self.bot.get_ignored_channel_ids(guild, db=db), await self.bot.get_ignore_overwrites_preference(guild, db=db), meta=get_meta(ctx), db=db)

                elif action_info[0] == 'REOPEN':
                    # Check if server is already opened
                    if guild_row[1] < guild_row[2]:
                        continue

                    # Reopen server
                    logger.info(f"Automatically reopening guild {guild_row[0]}.")
                    await self.bot.server_reopen(guild, json.loads(guild_row[3]), meta=report_meta, db=db)

                await asyncio.sleep(2) # Delay to prevent ratelimiting

            # Update status of action in calendar
            logger.info(f"{action_info[0]} task scheduled for {datetime.datetime.fromtimestamp(action_info[1]).isoformat()} ({action_info[1]}) completed.")
            await cal.execute("UPDATE CALENDAR SET COMPLETION_TIMESTAMP=?, COMPLETED=? WHERE SCHEDULED_TIMESTAMP=?", (datetime.datetime.now().timestamp(), 1, action_info[1]))
            
            # Mark older tasks as completed
            await cal.execute("UPDATE CALENDAR SET COMPLETED=?, COMPLETION_TIMESTAMP=? WHERE COMPLETED=0 AND SCHEDULED_TIMESTAMP<?", (1, datetime.datetime.now().timestamp(), action_info[1]))

            await cal.commit()
                
        finally:
            await cal.close()
            await db.close()

def setup(bot: utils.CurfewBot):
    bot.add_cog(AutoLockdownCog(bot))