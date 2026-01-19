from .access import Access


async def setup(bot):
    await bot.add_cog(Access(bot))
