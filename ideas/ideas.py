import asyncio
import logging

import httpx
from redbot.core import commands

log = logging.getLogger("red.cogs.ideas")


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

    @commands.command()
    @commands.is_owner()
    async def suggest(self, ctx, title: str, *, description: str):
        """Suggest a new idea by creating a GitHub issue

        The idea will be created as an issue in the GitHub repository
        and assigned to 'copilot' for tracking.

        Usage: [p]suggest "Title of idea" Description of the idea goes here
        """
        # Get the GitHub API token
        api_keys = await self.bot.get_shared_api_tokens("github")
        github_token = api_keys.get("token")

        if not github_token:
            await ctx.send(
                "GitHub API token is not set. "
                "Please set it using: `[p]set api github token <your_token>`"
            )
            return

        # Send a "working" message
        async with ctx.typing():
            # Create the issue on GitHub
            issue_data = await create_github_issue(
                token=github_token,
                repo_owner="psykzz",
                repo_name="cogs",
                title=title,
                body=description,
                assignees=["copilot-swe-agent"]
            )

        if issue_data:
            issue_url = issue_data.get("html_url")
            await ctx.send(f"✅ Idea submitted successfully!\n{issue_url}")
        else:
            await ctx.send("❌ Failed to create the GitHub issue. Please check the logs for details.")
