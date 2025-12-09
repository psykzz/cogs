from .secret_santa import SecretSanta

__red_end_user_data_statement__ = (
    "This cog stores user IDs for Secret Santa event participation, "
    "gift status tracking, and anonymous message relay."
)


async def setup(bot):
    await bot.add_cog(SecretSanta(bot))
