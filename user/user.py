import discord
from redbot.core import commands


class User(commands.Cog):
    """Manage bot user settings"""

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.group(name="user", invoke_without_command=True)
    async def _user(self, ctx):
        """Manage bot user settings"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @_user.command(name="nick")
    async def _nick(self, ctx, *, nickname: str = None):
        """Change the bot's nickname in this guild

        Use without a nickname to reset to default.
        """
        try:
            await ctx.guild.me.edit(nick=nickname)
            if nickname:
                await ctx.send(f"✅ Nickname changed to: {nickname}")
            else:
                await ctx.send("✅ Nickname reset to default.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change my nickname.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change nickname: {e}")

    @commands.guild_only()
    @_user.command(name="avatar")
    async def _avatar(self, ctx):
        """Change the bot's avatar in this guild using an attached image

        Note: This changes the bot's avatar only in this server.
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach an image to use as the new avatar.")
            return

        attachment = ctx.message.attachments[0]

        # Check if the attachment is an image
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            await ctx.send("❌ The attachment must be an image file.")
            return

        try:
            # Download the image
            image_data = await attachment.read()

            # Change the bot's avatar in this guild
            await ctx.guild.me.edit(avatar=image_data)
            await ctx.send("✅ Avatar changed successfully in this server!")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change my avatar in this server.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change avatar: {e}")
        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")
