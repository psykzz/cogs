from .video_dl import VideoDownloader

__red_end_user_data_statement__ = (
    "This cog stores guild configuration data including enabled status, "
    "disabled channels, and disabled users. No personal user data is stored."
)


async def setup(bot):
    await bot.add_cog(VideoDownloader(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
