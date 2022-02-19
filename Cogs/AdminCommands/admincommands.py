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

logger = logging.getLogger('cog-serverconfig')

NAME = "Admin Commands"
DESCRIPTION = "Commands for server owners and admins to manually operate the bot."

class AdminCommandsCog(commands.Cog, name=NAME, description=DESCRIPTION):
    def __init__(self, bot: utils.CurfewBot):
        self.bot = bot

def setup(bot: utils.CurfewBot):
    bot.add_cog(AdminCommandsCog(bot))