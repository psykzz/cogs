import asyncio
import logging

import httpx
from redbot.core import Config, commands

log = logging.getLogger("red.cogs.ideas")

# Config identifier for Red-bot Config system
CONFIG_IDENTIFIER = 1494641512


async def create_github_issue(token, repo_owner, repo_name, title, body, assignees=None):
    """Create a GitHub issue using the GitHub API"""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "psykzz-cogs/1.0.0"
    }

    data = {
        "title": title,
        "body": body
    }

    if assignees:
        data["assignees"] = assignees

    max_attempts = 3
    attempt = 0

    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url, headers=headers, json=data, timeout=10.0)

            if r.status_code == 201:
                response_data = r.json()
                log.info(f"Successfully created GitHub issue: {response_data.get('html_url')}")
                return response_data
            else:
                attempt += 1
                log.warning(
                    f"Failed to create GitHub issue - Status: {r.status_code}, "
                    f"Attempt {attempt}/{max_attempts}"
                )
                log.warning(f"Response: {r.text}")
                await asyncio.sleep(2)
        except (httpx.ConnectTimeout, httpx.RequestError) as e:
            attempt += 1
            log.warning(
                f"GitHub API error: {type(e).__name__}: {str(e)}, "
                f"Attempt {attempt}/{max_attempts}"
            )
            await asyncio.sleep(2)

    log.error(f"Failed to create GitHub issue after {max_attempts} attempts")
    return None


class Ideas(commands.Cog):
    """Suggest ideas by creating GitHub issues"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=CONFIG_IDENTIFIER)

        default_global = {
            "repo_owner": "psykzz",
            "repo_name": "cogs",
            "allow_anyone": False,
        }
        self.config.register_global(**default_global)

    @commands.command()
    async def suggest(self, ctx, title: str, *, description: str):
        """Suggest a new idea by creating a GitHub issue

        The idea will be created as an issue in the GitHub repository
        and assigned to 'copilot' for tracking.

        Parameters
        ----------
        title : str
            Title of the suggestion
        description : str
            Detailed description of the suggestion

        Usage
        -----
        /suggest "Title of idea" Description of the idea goes here
        """
        # Check permissions
        allow_anyone = await self.config.allow_anyone()
        if not allow_anyone and not await self.bot.is_owner(ctx.author):
            await ctx.send(
                "❌ This command is currently restricted to the bot owner. "
                "Ask the bot owner to enable public suggestions with `[p]ideaset allowanyone True`",
                ephemeral=True
            )
            return

        # Get the GitHub API token
        api_keys = await self.bot.get_shared_api_tokens("github")
        github_token = api_keys.get("token")

        if not github_token:
            await ctx.send(
                "GitHub API token is not set. "
                "Please set it using: `[p]set api github token <your_token>`",
                ephemeral=True
            )
            return

        # Get repository settings from config
        repo_owner = await self.config.repo_owner()
        repo_name = await self.config.repo_name()

        # Defer to prevent timeout
        await ctx.defer(ephemeral=True)

        # Use typing indicator for API call
        async with ctx.typing():
            # Create the issue on GitHub
            issue_data = await create_github_issue(
                token=github_token,
                repo_owner=repo_owner,
                repo_name=repo_name,
                title=title,
                body=description,
                assignees=[]
            )

        if issue_data:
            issue_url = issue_data.get("html_url")
            await ctx.send(f"✅ Idea submitted successfully!\n{issue_url}", ephemeral=True)
        else:
            await ctx.send("❌ Failed to create the GitHub issue. Please check the logs for details.", ephemeral=True)

    @commands.hybrid_group(name="ideaset")
    @commands.is_owner()
    async def ideaset(self, ctx):
        """Configure the ideas cog settings"""
        if ctx.invoked_subcommand is None:
            # Show current settings when no subcommand is provided
            await ctx.invoke(self.ideaset_showsettings)

    @ideaset.command(name="showsettings")
    async def ideaset_showsettings(self, ctx):
        """Show current ideas cog settings"""
        await ctx.defer(ephemeral=True)
        
        repo_owner = await self.config.repo_owner()
        repo_name = await self.config.repo_name()
        allow_anyone = await self.config.allow_anyone()

        settings_msg = (
            f"**Ideas Cog Settings:**\n"
            f"Repository: `{repo_owner}/{repo_name}`\n"
            f"Allow anyone to suggest: `{allow_anyone}`"
        )
        await ctx.send(settings_msg, ephemeral=True)

    @ideaset.command(name="owner")
    async def ideaset_owner(self, ctx, owner: str):
        """Set the GitHub repository owner

        Parameters
        ----------
        owner : str
            GitHub username (e.g., psykzz)
        
        Example
        -------
        /ideaset owner psykzz
        """
        await ctx.defer(ephemeral=True)
        await self.config.repo_owner.set(owner)
        await ctx.send(f"✅ Repository owner set to: `{owner}`", ephemeral=True)

    @ideaset.command(name="repo")
    async def ideaset_repo(self, ctx, repo: str):
        """Set the GitHub repository name

        Parameters
        ----------
        repo : str
            Repository name (e.g., cogs)
        
        Example
        -------
        /ideaset repo cogs
        """
        await ctx.defer(ephemeral=True)
        await self.config.repo_name.set(repo)
        await ctx.send(f"✅ Repository name set to: `{repo}`", ephemeral=True)

    @ideaset.command(name="allowanyone")
    async def ideaset_allowanyone(self, ctx, enabled: bool):
        """Toggle whether anyone can use the suggest command

        Set to True to allow anyone, False to restrict to bot owner only.

        Parameters
        ----------
        enabled : bool
            True to allow anyone, False for bot owner only
        
        Example
        -------
        /ideaset allowanyone True
        """
        await ctx.defer(ephemeral=True)
        await self.config.allow_anyone.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"✅ Public suggestions {status}. Anyone can suggest: `{enabled}`", ephemeral=True)
