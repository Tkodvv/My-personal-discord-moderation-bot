# cogs/admin_alt.py
import os, logging, discord
from discord.ext import commands
from roblox_alts import get_alt_public

log = logging.getLogger(__name__)

def _enabled():
    return os.getenv("MOD_ENABLE_RBX_ALT", "false").lower() in {"1","true","yes","y"}

class Alts(commands.Cog):
    """Admin-only alt viewer (read-only, no credentials)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="alt")
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 8, commands.BucketType.guild)
    async def alt(self, ctx: commands.Context):
        if not _enabled():
            await ctx.send("alts feature is disabled.")
            return
        try:
            async with ctx.typing():
                prof = await get_alt_public()
                if not prof or not prof.get("username"):
                    await ctx.send("couldn't fetch an alt right now.")
                    return

                embed = discord.Embed(
                    title=prof.get("displayName") or prof.get("username") or "Roblox Alt",
                    description=prof.get("bio") or "no bio",
                    color=0x00b2ff,
                )
                if prof.get("avatarUrl"):
                    embed.set_thumbnail(url=prof["avatarUrl"])
                embed.add_field(name="Username", value=prof["username"], inline=True)

                meta = prof.get("meta") or {}
                if isinstance(meta, dict):
                    note = str(meta.get("note", ""))[:150]
                    expires = meta.get("expiresAt") or meta.get("expires_at")
                    if note:   embed.add_field(name="Note", value=note, inline=False)
                    if expires:embed.add_field(name="Expires", value=str(expires), inline=True)

                await ctx.send(embed=embed)

        except commands.CommandOnCooldown as e:
            await ctx.send(f"slow down — try again in {e.retry_after:.1f}s")
        except commands.MissingPermissions:
            await ctx.send("you need Manage Server to use this.")
        except Exception as e:
            log.error("!alt failed: %s", e)
            await ctx.send("couldn't fetch a random alt rn, try again later.")

async def setup(bot: commands.Bot):  # discord.py 2.x
    await bot.add_cog(Alts(bot))

def setup_legacy(bot: commands.Bot):  # for older discord.py
    bot.add_cog(Alts(bot))
