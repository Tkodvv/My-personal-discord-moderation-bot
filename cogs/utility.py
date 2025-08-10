# -*- coding: utf-8 -*-
"""
Utility Cog
Contains utility commands like userinfo, avatar, server info, status lists, etc.
"""

import logging
import re
import asyncio
import math
import os
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from discord.utils import utcnow, format_dt
from datetime import timedelta
from typing import Optional, List, Dict, Set


class UtilityCog(commands.Cog):
    """Utility commands cog."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.start_time = utcnow()  # tz-aware

        # message_id -> set(str(emoji)) allowed for polls
        self._poll_reaction_whitelist: Dict[int, Set[str]] = {}

    async def delete_command_message(self, ctx):
        """Helper to delete the command message."""
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # ---------- emoji & formatting helpers for /embed ----------

    def _emojiize_unicode(self, text: str) -> str:
        """Map common :shortcodes: to real Unicode emojis (ASCII-escaped)."""
        mapping = {
            ":blue_diamond:": "\U0001F537",
            ":diamond:": "\U0001F537",
            ":lock:": "\U0001F512",
            ":check:": "\u2705",
            ":white_check_mark:": "\u2705",
            ":green_circle:": "\U0001F7E2",
            ":yellow_circle:": "\U0001F7E1",
            ":red_circle:": "\U0001F534",
            ":sparkles:": "\u2728",
            ":warning:": "\u26A0\uFE0F",
            ":info:": "\u2139\uFE0F",
        }
        for k, v in mapping.items():
            text = text.replace(k, v)
        return text

    def _emojiize_server(self, text: str, guild: Optional[discord.Guild]) -> str:
        """Replace :name: with the actual custom emoji from this guild if it exists."""
        if not guild or ":" not in text:
            return text

        name_to_emoji = {e.name.lower(): e for e in guild.emojis}
        for m in set(re.findall(r":([A-Za-z0-9_]+):", text)):
            e = name_to_emoji.get(m.lower())
            if e:
                rep = f"<{'a' if e.animated else ''}:{e.name}:{e.id}>"
                text = re.sub(fr":{re.escape(m)}:", rep, text)
        return text

    def _auto_bullets(self, text: str) -> str:
        """
        If user pasted a single paragraph with separators, add line breaks.
        - If there are already newlines, do nothing.
        - Otherwise split on common separators and rebuild with newlines.
        """
        if "\n" in text:
            return text

        text = text.replace("\\n", "\n")
        if "\n" in text:
            return text

        for sep in [" \u2022 ", " | ", "; ", " - "]:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) > 1:
                    head, rest = parts[0], parts[1:]
                    formatted = [head]
                    for item in rest:
                        # keep existing leading emoji/emojiID bullets
                        if re.match(r"^[\u2705\U0001F512\U0001F537\u2022\U0001F7E2\U0001F7E1\U0001F534\u2728\u26A0\uFE0F\u2139\uFE0F<:.*?:\d+]", item):
                            formatted.append(item)
                        else:
                            formatted.append(f"\u2022 {item}")
                    return "\n".join(formatted)
        return text

    def _emojiize_and_format(self, text: Optional[str], guild: Optional[discord.Guild]) -> Optional[str]:
        if text is None:
            return None
        text = text.replace("\\n", "\n")
        text = self._emojiize_unicode(text)
        text = self._emojiize_server(text, guild)
        text = self._auto_bullets(text)
        return text

    # =========================
    # /embed (two-step modal builder with preview)
    # =========================

    class _EmbedState:
        """Hold in-progress embed data per user."""
        __slots__ = ("channel_id", "title", "description", "color_hex",
                     "footer", "timestamp", "image_url", "thumb_url",
                     "author_name", "author_icon")

        def __init__(self, channel_id: Optional[int]):
            self.channel_id = channel_id
            self.title: Optional[str] = None
            self.description: Optional[str] = None
            self.color_hex: Optional[str] = None
            self.footer: Optional[str] = None
            self.timestamp: bool = False
            self.image_url: Optional[str] = None
            self.thumb_url: Optional[str] = None
            self.author_name: Optional[str] = None
            self.author_icon: Optional[str] = None

    @staticmethod
    def _parse_color_hex(c: Optional[str]) -> discord.Color:
        if not c:
            return discord.Color.blue()
        c = c.strip().lower()
        if c.startswith("#"):
            c = c[1:]
        try:
            value = int(c, 16)
            value = max(0, min(value, 0xFFFFFF))
            return discord.Color(value)
        except Exception:
            return discord.Color.blue()

    def _build_embed_from_state(self, guild: Optional[discord.Guild], st: "_EmbedState") -> discord.Embed:
        title = self._emojiize_and_format(st.title, guild)
        desc = self._emojiize_and_format(st.description, guild)
        footer = self._emojiize_and_format(st.footer, guild)
        author_name = self._emojiize_and_format(st.author_name, guild)

        embed = discord.Embed(
            title=title or None,
            description=desc or None,
            color=self._parse_color_hex(st.color_hex)
        )
        if author_name:
            if st.author_icon and (st.author_icon.startswith("http://") or st.author_icon.startswith("https://")):
                embed.set_author(name=author_name, icon_url=st.author_icon)
            else:
                embed.set_author(name=author_name)

        if st.image_url and (st.image_url.startswith("http://") or st.image_url.startswith("https://")):
            embed.set_image(url=st.image_url)
        if st.thumb_url and (st.thumb_url.startswith("http://") or st.thumb_url.startswith("https://")):
            embed.set_thumbnail(url=st.thumb_url)
        if footer:
            embed.set_footer(text=footer)
        if st.timestamp:
            embed.add_field(name="Time", value=format_dt(utcnow(), style="F"), inline=False)
        return embed

    class EmbedBasicModal(discord.ui.Modal, title="Create Embed - Basic"):
        """First modal: 5 inputs max (Discord limit)."""
        def __init__(self, cog: "UtilityCog", state: "UtilityCog._EmbedState"):
            super().__init__(timeout=300)
            self.cog = cog
            self.state = state

            self.title_input = discord.ui.TextInput(
                label="Title",
                required=False,
                max_length=256,
                style=discord.TextStyle.short,
                placeholder="Optional title"
            )
            self.desc_input = discord.ui.TextInput(
                label="Description",
                required=False,
                style=discord.TextStyle.paragraph,
                placeholder="Supports :shortcodes:, server emojis (:YourEmoji:), and \\n for new lines"
            )
            self.color_input = discord.ui.TextInput(
                label="Color (hex like #00FF88) [optional]",
                required=False,
                max_length=7
            )
            self.footer_input = discord.ui.TextInput(
                label="Footer [optional]",
                required=False,
                max_length=2048
            )
            self.time_input = discord.ui.TextInput(
                label="Add current time? (yes/no) [optional]",
                required=False,
                placeholder="yes or no"
            )

            for item in (self.title_input, self.desc_input, self.color_input, self.footer_input, self.time_input):
                self.add_item(item)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            if not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message("❌ You need **Manage Messages** to use `/embed`.", ephemeral=True)
                return

            self.state.title = (self.title_input.value or None)
            self.state.description = (self.desc_input.value or None)
            self.state.color_hex = (self.color_input.value or None)
            self.state.footer = (self.footer_input.value or None)
            self.state.timestamp = (self.time_input.value or "").strip().lower() in ("y", "yes", "true", "t", "1")

            await interaction.response.send_message(
                "✅ Basic details saved. Use the buttons below to **Send** or add **Advanced** fields.",
                view=self.cog.EmbedPreviewView(self.cog, self.state),
                ephemeral=True
            )

    class EmbedAdvancedModal(discord.ui.Modal, title="Create Embed - Advanced"):
        """Second modal for optional fields (4 inputs)."""
        def __init__(self, cog: "UtilityCog", state: "UtilityCog._EmbedState"):
            super().__init__(timeout=300)
            self.cog = cog
            self.state = state

            self.image_input = discord.ui.TextInput(label="Image URL [optional]", required=False)
            self.thumb_input = discord.ui.TextInput(label="Thumbnail URL [optional]", required=False)
            self.author_name_input = discord.ui.TextInput(label="Author name [optional]", required=False, max_length=256)
            self.author_icon_input = discord.ui.TextInput(label="Author icon URL [optional]", required=False)

            for item in (self.image_input, self.thumb_input, self.author_name_input, self.author_icon_input):
                self.add_item(item)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            self.state.image_url = (self.image_input.value or None)
            self.state.thumb_url = (self.thumb_input.value or None)
            self.state.author_name = (self.author_name_input.value or None)
            self.state.author_icon = (self.author_icon_input.value or None)

            await interaction.response.edit_message(
                content="✅ Advanced fields added. Review preview and **Send** when ready.",
                view=self.cog.EmbedPreviewView(self.cog, self.state)
            )

    class EmbedPreviewView(discord.ui.View):
        """Ephemeral preview controls."""
        def __init__(self, cog: "UtilityCog", state: "UtilityCog._EmbedState"):
            super().__init__(timeout=300)
            self.cog = cog
            self.state = state

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return True

        @discord.ui.button(label="Add Advanced", style=discord.ButtonStyle.secondary)
        async def add_adv(self, interaction: discord.Interaction, _button: discord.ui.Button):
            await interaction.response.send_modal(self.cog.EmbedAdvancedModal(self.cog, self.state))

        @discord.ui.button(label="Preview", style=discord.ButtonStyle.primary)
        async def preview(self, interaction: discord.Interaction, _button: discord.ui.Button):
            embed = self.cog._build_embed_from_state(interaction.guild, self.state)
            await interaction.response.edit_message(content="(Preview below - ephemeral)", embed=embed, view=self)

        @discord.ui.button(label="Send", style=discord.ButtonStyle.success)
        async def send(self, interaction: discord.Interaction, _button: discord.ui.Button):
            channel = None
            if self.state.channel_id and interaction.guild:
                channel = interaction.guild.get_channel(self.state.channel_id)
            channel = channel or interaction.channel

            try:
                embed = self.cog._build_embed_from_state(interaction.guild, self.state)
                await channel.send(embed=embed)
            except discord.Forbidden:
                await interaction.response.edit_message(content="❌ I can't send messages in that channel.", embed=None, view=None)
                return
            except Exception as e:
                await interaction.response.edit_message(content=f"❌ Failed to send embed: `{e}`", embed=None, view=None)
                return

            await interaction.response.edit_message(content=f"✅ Embed sent to {channel.mention}", embed=None, view=None)

    @app_commands.command(name="embed", description="Create and send a custom embed (supports server emojis).")
    @app_commands.describe(channel="Channel to send to (default: here)")
    async def embed(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You need **Manage Messages** to use `/embed`.", ephemeral=True)
            return

        state = self._EmbedState(channel.id if channel else None)
        await interaction.response.send_modal(self.EmbedBasicModal(self, state))

    # =========================
    # /cat (random cat images via TheCatAPI) — followup to end "thinking"
    # =========================
    @app_commands.command(name="cat", description="Send random cat image(s) (1–5).")
    @app_commands.describe(count="How many? (1–5)")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.user.id))
    async def cat(self, interaction: discord.Interaction, count: Optional[int] = 1):
        """Fetch random cat images using TheCatAPI and send raw URLs (no embeds)."""
        n = max(1, min(count or 1, 5))
        await interaction.response.defer(thinking=True)

        api_key = os.getenv("CAT_API_KEY")
        url = "https://api.thecatapi.com/v1/images/search"
        params = {"limit": n, "size": "full"}
        headers = {"x-api-key": api_key} if api_key else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=15) as r:
                    if r.status != 200:
                        await interaction.followup.send("❌ Cat API error. Try again later.", ephemeral=True)
                        return
                    data = await r.json()
        except Exception:
            await interaction.followup.send("❌ Couldn’t reach the cat server. Try again later.", ephemeral=True)
            return

        if not isinstance(data, list) or not data:
            await interaction.followup.send("❌ No cats found.", ephemeral=True)
            return

        # Use followup for the first send to stop the spinner,
        # then send any remaining images directly to the channel.
        sent_any = False
        for item in data[:n]:
            img = item.get("url")
            if not img:
                continue
            if not sent_any:
                await interaction.followup.send(img)  # ends "thinking…"
                sent_any = True
            else:
                await interaction.channel.send(img)

        if not sent_any:
            await interaction.followup.send("❌ Cat API returned no usable images.", ephemeral=True)

    @commands.command(name="cat")
    async def prefix_cat(self, ctx, count: Optional[int] = 1):
        """Prefix version of cat command. Auto-deletes the invoking message and sends raw URLs."""
        await self.delete_command_message(ctx)
        try:
            n = max(1, min(int(count or 1), 5))
        except Exception:
            n = 1

        api_key = os.getenv("CAT_API_KEY")
        url = "https://api.thecatapi.com/v1/images/search"
        params = {"limit": n, "size": "full"}
        headers = {"x-api-key": api_key} if api_key else {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=15) as r:
                    if r.status != 200:
                        await ctx.send("❌ Cat API error. Try again later.", delete_after=5)
                        return
                    data = await r.json()
        except Exception:
            await ctx.send("❌ Couldn’t reach the cat server. Try again later.", delete_after=5)
            return

        if not isinstance(data, list) or not data:
            await ctx.send("❌ No cats found.", delete_after=5)
            return

        for item in data[:n]:
            img = item.get("url")
            if img:
                await ctx.send(img)

    # =========================
    # /banner (user banner)
    # =========================
    @app_commands.command(name="banner", description="Show a user's profile banner (if set).")
    @app_commands.describe(member="The member to get the banner of (default: you)")
    async def banner(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user  # type: ignore[assignment]
        try:
            user = await interaction.client.fetch_user(member.id)  # type: ignore[arg-type]
        except Exception:
            await interaction.response.send_message("❌ Couldn't fetch that user.", ephemeral=True)
            return

        if user.banner:
            banner_url = user.banner.replace(size=2048).url
            embed = discord.Embed(
                title=f"{member.display_name}'s Banner",
                color=member.color if isinstance(member, discord.Member) and member.color.value else discord.Color.blue()
            )
            embed.set_image(url=banner_url)

            links = []
            if user.banner.is_animated():
                links.append(f"[GIF]({user.banner.replace(format='gif', size=2048).url})")
            links.extend([
                f"[PNG]({user.banner.replace(format='png', size=2048).url})",
                f"[JPG]({user.banner.replace(format='jpg', size=2048).url})",
                f"[WEBP]({user.banner.replace(format='webp', size=2048).url})",
            ])
            embed.add_field(name="Download", value=" | ".join(links), inline=False)
            await interaction.response.send_message(embed=embed)
        elif user.accent_color:
            embed = discord.Embed(
                title=f"{member.display_name} has no banner",
                description=f"Accent color: `{user.accent_color}`",
                color=user.accent_color
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ That user doesn't have a banner set.", ephemeral=True)

    # =========================
    # /poll (auto-close + winner + reaction lock)
    # =========================
    @app_commands.command(name="poll", description="Create a quick poll with up to 10 options (auto-close + winner).")
    @app_commands.describe(
        question="The poll question",
        options="Options separated by | (leave empty for Yes/No ✅/❌)",
        channel="Channel to send to (default: here)",
        multi_vote="Allow voting on multiple options (default: false)",
        duration="Auto-close after time like 10m, 2h, 1d2h (optional)"
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        multi_vote: Optional[bool] = False,
        duration: Optional[str] = None
    ):
        target_channel = channel or interaction.channel

        # Parse options
        if options:
            raw = [opt.strip() for opt in options.split("|")]
            opts = [o for o in raw if o]
            if not opts:
                opts = ["Yes", "No"]
        else:
            opts = ["Yes", "No"]

        if len(opts) > 10:
            await interaction.response.send_message("❌ Max 10 options.", ephemeral=True)
            return

        # Emoji set
        number_emojis = [
            "\u0031\uFE0F\u20E3", "\u0032\uFE0F\u20E3", "\u0033\uFE0F\u20E3",
            "\u0034\uFE0F\u20E3", "\u0035\uFE0F\u20E3", "\u0036\uFE0F\u20E3",
            "\u0037\uFE0F\u20E3", "\u0038\uFE0F\u20E3", "\u0039\uFE0F\u20E3", "\U0001F51F"
        ]
        reactions = ["\u2705", "\u274C"] if len(opts) == 2 else number_emojis[:len(opts)]

        # Build embed
        embed = discord.Embed(
            title="\U0001F4CA Poll",
            description=f"**{question}**",
            color=discord.Color.blurple()
        )
        if len(opts) == 2 and reactions == ["\u2705", "\u274C"]:
            body = f"{reactions[0]} {opts[0]}\n{reactions[1]} {opts[1]}"
        else:
            lines = [f"{reactions[i]} {opts[i]}" for i in range(len(opts))]
            body = "\n".join(lines)
        embed.add_field(
            name="Options" if len(opts) != 2 else "Vote",
            value=body,
            inline=False
        )

        seconds = None
        if duration:
            seconds = self._parse_duration_string(duration)
            if seconds and seconds > 0:
                closes_at = utcnow() + timedelta(seconds=seconds)
                embed.add_field(name="Closes", value=f"{format_dt(closes_at, style='R')} ({format_dt(closes_at, style='F')})", inline=False)
            else:
                seconds = None  # invalid -> ignore

        embed.set_footer(text="Multiple votes allowed" if multi_vote else "Single vote recommended")

        try:
            msg = await target_channel.send(embed=embed)
            # Add reactions & set whitelist
            for r in reactions:
                await msg.add_reaction(r)
            self._poll_reaction_whitelist[msg.id] = set(reactions)

            if target_channel != interaction.channel:
                await interaction.response.send_message(f"✅ Poll sent to {target_channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Poll created.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I can't send messages or add reactions there.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to create poll: `{e}`", ephemeral=True)
            return

        # Auto-close scheduling
        if seconds:
            self.bot.loop.create_task(self._close_poll_after(
                msg.channel.id, msg.id, opts, reactions, multi_vote, seconds
            ))

    async def _close_poll_after(
        self,
        channel_id: int,
        message_id: int,
        opts: List[str],
        reactions: List[str],
        multi_vote: bool,
        seconds: int
    ):
        """Sleep for `seconds`, then tally and close."""
        await asyncio.sleep(seconds)

        # Fetch message fresh
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)  # type: ignore[assignment]
            message: discord.Message = await channel.fetch_message(message_id)  # type: ignore[assignment]
        except Exception:
            self._poll_reaction_whitelist.pop(message_id, None)
            return

        # Tally votes
        emoji_to_index: Dict[str, int] = {reactions[i]: i for i in range(len(reactions))}
        voters_per_reaction: List[Set[int]] = [set() for _ in reactions]

        for reaction in message.reactions:
            key = None
            if isinstance(reaction.emoji, str) and reaction.emoji in emoji_to_index:
                key = reaction.emoji
            if key is None:
                continue

            idx = emoji_to_index[key]
            try:
                async for user in reaction.users():
                    if user.bot:
                        continue
                    voters_per_reaction[idx].add(user.id)
            except discord.Forbidden:
                continue

        if multi_vote:
            counts = [len(s) for s in voters_per_reaction]
            total_ballots = len(set().union(*voters_per_reaction)) if voters_per_reaction else 0
        else:
            user_choice: Dict[int, int] = {}
            for i in range(len(reactions)):
                for uid in voters_per_reaction[i]:
                    if uid not in user_choice:
                        user_choice[uid] = i
            counts = [0] * len(reactions)
            for idx in user_choice.values():
                counts[idx] += 1
            total_ballots = len(user_choice)

        total_votes = sum(counts)

        # Build results body with percentages
        def pct(n: int, d: int) -> str:
            return f"{(n * 100 / d):.1f}%" if d > 0 else "0.0%"

        lines = []
        for i, c in enumerate(counts):
            label = opts[i]
            emoji = reactions[i]
            lines.append(f"{emoji} **{label}** — **{c}** ({pct(c, total_votes)})")
        result_body = "\n".join(lines) if lines else "No votes."

        # Determine winner(s)
        if total_votes > 0:
            max_votes = max(counts)
            winner_indexes = [i for i, c in enumerate(counts) if c == max_votes]
            if len(winner_indexes) == 1:
                wi = winner_indexes[0]
                winner_text = f"{reactions[wi]} **{opts[wi]}** with **{counts[wi]}** ({pct(counts[wi], total_votes)})"
            else:
                winners_str = ", ".join(f"{reactions[i]} **{opts[i]}**" for i in winner_indexes)
                winner_text = f"Tie between {winners_str} — **{max_votes}** each"
            winner_field_name = "Winners" if len(winner_indexes) > 1 else "Winner"
        else:
            winner_text = "No votes cast."
            winner_field_name = "Winner"

        # Edit embed
        try:
            e = message.embeds[0] if message.embeds else discord.Embed(title="\U0001F4CA Poll", color=discord.Color.blurple())
            e.title = "\U0001F4CA Poll (closed)"
            # keep any non-options fields; drop Options/Vote/Closes
            keep = []
            for f in e.fields:
                if f.name in ("Options", "Vote", "Closes"):
                    continue
                keep.append(f)
            e.clear_fields()
            for f in keep:
                e.add_field(name=f.name, value=f.value, inline=f.inline)
            e.add_field(name="Results", value=result_body, inline=False)
            e.add_field(name=winner_field_name, value=winner_text, inline=False)
            e.set_footer(text=f"Poll closed • Total ballots: {total_ballots}")
            await message.edit(embed=e)
        except Exception:
            pass

        # Try to clear reactions to lock the poll
        try:
            await message.clear_reactions()
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Cleanup whitelist
        self._poll_reaction_whitelist.pop(message_id, None)

    # Reaction lock enforcement (removes any reaction not in the whitelist)
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore the bot's own reactions
        if payload.user_id == (self.bot.user.id if self.bot.user else None):
            return

        allowed = self._poll_reaction_whitelist.get(payload.message_id)
        if not allowed:
            return

        emoji_str = str(payload.emoji)
        if emoji_str in allowed:
            return  # allowed

        # Remove the unauthorized reaction
        try:
            channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)  # type: ignore[assignment]
            message: discord.Message = await channel.fetch_message(payload.message_id)  # type: ignore[assignment]
            user = payload.member or await self.bot.fetch_user(payload.user_id)
            await message.remove_reaction(payload.emoji, user)
        except Exception:
            pass

    # =========================
    # /remindme (simple reminders)
    # =========================
    @app_commands.command(name="remindme", description="Set a reminder (e.g., 10m, 2h, 1d). Not persistent across restarts.")
    @app_commands.describe(
        when="Time from now like 10m, 2h, 1d, or combos like 1h30m",
        text="What should I remind you about?",
        dm="Send the reminder as a DM (default: true)"
    )
    async def remindme(self, interaction: discord.Interaction, when: str, text: str, dm: Optional[bool] = True):
        total_seconds = self._parse_duration_string(when)
        if total_seconds is None or total_seconds <= 0:
            await interaction.response.send_message("❌ Invalid duration. Try formats like `10m`, `2h`, `1d2h`, `45m30s`.", ephemeral=True)
            return

        fire_time = utcnow() + timedelta(seconds=total_seconds)
        target = interaction.user if dm else interaction.channel

        await interaction.response.send_message(
            f"⏰ I’ll remind you **{format_dt(fire_time, style='R')}** "
            f"({format_dt(fire_time, style='F')}).",
            ephemeral=True
        )

        async def _task():
            try:
                await asyncio.sleep(total_seconds)
                embed = discord.Embed(
                    title="⏰ Reminder",
                    description=text,
                    color=discord.Color.green()
                )
                embed.add_field(name="Requested", value=f"{interaction.user.mention}", inline=True)
                embed.add_field(name="Set", value=format_dt(utcnow(), style="F"), inline=True)
                await target.send(embed=embed)  # type: ignore[arg-type]
            except Exception:
                pass  # best-effort

        self.bot.loop.create_task(_task())

    @staticmethod
    def _parse_duration_string(s: str) -> Optional[int]:
        s = s.strip().lower().replace(" ", "")
        if not s:
            return None
        pattern = r"^(?:(?P<d>\d+)d)?(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$"
        m = re.match(pattern, s)
        if not m:
            return None
        days = int(m.group("d") or 0)
        hours = int(m.group("h") or 0)
        minutes = int(m.group("m") or 0)
        seconds = int(m.group("s") or 0)
        total = days*86400 + hours*3600 + minutes*60 + seconds
        return total if total > 0 else None

    # =========================
    # /calc (safe calculator)
    # =========================
    @app_commands.command(name="calc", description="Calculate a math expression (safe).")
    @app_commands.describe(expression="The math expression to calculate (e.g., 5*(3+2), sin(pi/2))")
    async def calc(self, interaction: discord.Interaction, expression: str):
        """Safely evaluate a basic math expression using math.* and a few builtins."""
        allowed: Dict[str, object] = {
            **{k: v for k, v in math.__dict__.items() if not k.startswith("__")},
            "abs": abs, "round": round, "min": min, "max": max
        }
        try:
            code = compile(expression, "<calc>", "eval")
            for name in code.co_names:
                if name not in allowed:
                    await interaction.response.send_message(
                        f"❌ Invalid name or function: `{name}`", ephemeral=True
                    )
                    return
            result = eval(code, {"__builtins__": {}}, allowed)
            embed = discord.Embed(
                title="🧮 Calculator",
                color=discord.Color.green()
            )
            embed.add_field(name="Expression", value=f"```{expression}```", inline=False)
            embed.add_field(name="Result", value=f"```{result}```", inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)

    # =========================
    # Existing utility commands
    # =========================
    @app_commands.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(member="The member to get information about")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user

        if isinstance(member, discord.User) and interaction.guild:
            member = interaction.guild.get_member(member.id)
            if not member:
                await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
                return

        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ User information is only available for server members.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"User Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        created_at = int(member.created_at.timestamp())
        embed.add_field(name="Account Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        if member.joined_at:
            joined_at = int(member.joined_at.timestamp())
            embed.add_field(name="Joined Server", value=f"<t:{joined_at}:F> (<t:{joined_at}:R>)", inline=False)
        status_emoji = {
            discord.Status.online: "\U0001F7E2",
            discord.Status.idle: "\U0001F7E1",
            discord.Status.dnd: "\U0001F534",
            discord.Status.offline: "\u26AB",
        }
        embed.add_field(name="Status", value=f"{status_emoji.get(member.status, '✅')} {member.status.name.title()}", inline=True)
        roles = [role.mention for role in member.roles[1:]]
        if roles:
            roles_text = ", ".join(roles) if len(", ".join(roles)) <= 1024 else f"{len(roles)} roles"
            embed.add_field(name=f"Roles [{len(roles)}]", value=roles_text, inline=False)
        if member.guild_permissions.administrator:
            embed.add_field(name="Permissions", value="Administrator", inline=True)
        elif any([
            member.guild_permissions.kick_members,
            member.guild_permissions.ban_members,
            member.guild_permissions.manage_messages,
            member.guild_permissions.manage_channels
        ]):
            embed.add_field(name="Permissions", value="Moderator", inline=True)
        if member.premium_since:
            boost_since = int(member.premium_since.timestamp())
            embed.add_field(name="Boosting Since", value=f"<t:{boost_since}:F>", inline=True)
        if member.timed_out_until:
            timeout_until = int(member.timed_out_until.timestamp())
            embed.add_field(name="Timed Out Until", value=f"<t:{timeout_until}:F>", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(member="The member to get the avatar of")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user

        if isinstance(member, discord.User) and interaction.guild:
            member = interaction.guild.get_member(member.id)
            if not member:
                await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
                return

        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_image(url=member.display_avatar.url)
        avatar_formats = []
        if member.display_avatar.is_animated():
            avatar_formats.append(f"[GIF]({member.display_avatar.replace(format='gif', size=1024).url})")
        avatar_formats.extend([
            f"[PNG]({member.display_avatar.replace(format='png', size=1024).url})",
            f"[JPG]({member.display_avatar.replace(format='jpg', size=1024).url})",
            f"[WEBP]({member.display_avatar.replace(format='webp', size=1024).url})"
        ])
        embed.add_field(name="Download Links", value=" | ".join(avatar_formats), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Server Information - {guild.name}",
            color=discord.Color.blue()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Server Name", value=guild.name, inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        created_at = int(guild.created_at.timestamp())
        embed.add_field(name="Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        total_members = guild.member_count
        online_members = sum(1 for member in guild.members if member.status != discord.Status.offline)
        embed.add_field(name="Members", value=f"Total: {total_members}\nOnline: {online_members}", inline=True)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        embed.add_field(name="Channels", value=f"Text: {text_channels}\nVoice: {voice_channels}\nCategories: {categories}", inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count or 0, inline=True)
        if guild.features:
            features = [feature.replace('_', ' ').title() for feature in guild.features]
            features_text = ", ".join(features) if len(", ".join(features)) <= 1024 else f"{len(features)} features"
            embed.add_field(name="Features", value=features_text, inline=False)
        await interaction.response.send_message(embed=embed)

    # =========================
    # Status lists (who is Online/Idle/DND/Offline)
    # =========================
    def _presence_enabled(self, guild: Optional[discord.Guild]) -> bool:
        intents = getattr(self.bot, "intents", None)
        return bool(intents and getattr(intents, "presences", False))

    def _format_member_list(self, members: List[discord.Member], limit: int = 30) -> str:
        """Return a newline list of member display names, limited."""
        if not members:
            return "_None_"
        names = [m.display_name for m in members[:limit]]
        extra = len(members) - len(names)
        body = "\n".join(f"• {n}" for n in names)
        if extra > 0:
            body += f"\n…and {extra} more"
        return body

    @app_commands.command(name="status", description="Show who is Online/Idle/DND/Offline (optionally filter).")
    @app_commands.describe(status="Optional filter: online | idle | dnd | offline")
    async def status(self, interaction: discord.Interaction, status: Optional[str] = None):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        online = [m for m in guild.members if m.status == discord.Status.online]
        idle = [m for m in guild.members if m.status == discord.Status.idle]
        dnd = [m for m in guild.members if m.status == discord.Status.dnd]
        offline = [m for m in guild.members if m.status == discord.Status.offline]

        def filter_bots(lst: List[discord.Member]) -> List[discord.Member]:
            return [m for m in lst if not m.bot]

        e = discord.Embed(title=f"{guild.name} Presence", color=discord.Color.blurple())
        e.set_thumbnail(url=guild.icon.url if guild.icon else None)

        warn = ""
        if not self._presence_enabled(guild):
            warn = "\n\n_Heads up: Presence Intent is not enabled — lists may be incomplete. Enable `Server Members Intent` and `Presence Intent` in the Dev Portal and set `intents.presences = True` in your code._"

        if status:
            key = status.lower().strip()
            mapping = {
                "online": ("\U0001F7E2 Online", online),
                "idle": ("\U0001F7E1 Idle", idle),
                "dnd": ("\U0001F534 Do Not Disturb", dnd),
                "offline": ("\u26AB Offline", offline),
            }
            if key not in mapping:
                await interaction.response.send_message("❌ Invalid status. Use: online, idle, dnd, offline.", ephemeral=True)
                return
            label, lst = mapping[key]
            humans = filter_bots(lst)
            e.add_field(name=f"{label} ({len(lst)})", value=self._format_member_list(humans), inline=False)
            if warn:
                e.description = warn
            await interaction.response.send_message(embed=e)
            return

        e.add_field(name=f"\U0001F7E2 Online ({len(online)})", value=self._format_member_list(filter_bots(online)), inline=False)
        e.add_field(name=f"\U0001F7E1 Idle ({len(idle)})", value=self._format_member_list(filter_bots(idle)), inline=False)
        e.add_field(name=f"\U0001F534 DND ({len(dnd)})", value=self._format_member_list(filter_bots(dnd)), inline=False)
        e.add_field(name=f"\u26AB Offline ({len(offline)})", value=self._format_member_list(filter_bots(offline)), inline=False)
        if warn:
            e.description = warn
        await interaction.response.send_message(embed=e)

    @commands.command(name="status")
    async def prefix_status(self, ctx, status: Optional[str] = None):
        """Prefix version of status (auto-deletes invoke)."""
        await self.delete_command_message(ctx)
        guild = ctx.guild
        if not guild:
            return

        online = [m for m in guild.members if m.status == discord.Status.online]
        idle = [m for m in guild.members if m.status == discord.Status.idle]
        dnd = [m for m in guild.members if m.status == discord.Status.dnd]
        offline = [m for m in guild.members if m.status == discord.Status.offline]

        def filter_bots(lst: List[discord.Member]) -> List[discord.Member]:
            return [m for m in lst if not m.bot]

        e = discord.Embed(title=f"{guild.name} Presence", color=discord.Color.blurple())
        e.set_thumbnail(url=guild.icon.url if guild.icon else None)

        warn = ""
        if not self._presence_enabled(guild):
            warn = "\n\n_Heads up: Presence Intent is not enabled — lists may be incomplete._"

        if status:
            key = status.lower().strip()
            mapping = {
                "online": ("\U0001F7E2 Online", online),
                "idle": ("\U0001F7E1 Idle", idle),
                "dnd": ("\U0001F534 Do Not Disturb", dnd),
                "offline": ("\u26AB Offline", offline),
            }
            if key not in mapping:
                await ctx.send("❌ Invalid status. Use: online, idle, dnd, offline.", delete_after=5)
                return
            label, lst = mapping[key]
            humans = filter_bots(lst)
            e.add_field(name=f"{label} ({len(lst)})", value=self._format_member_list(humans), inline=False)
            if warn:
                e.description = warn
            await ctx.send(embed=e)
            return

        e.add_field(name=f"\U0001F7E2 Online ({len(online)})", value=self._format_member_list(filter_bots(online)), inline=False)
        e.add_field(name=f"\U0001F7E1 Idle ({len(idle)})", value=self._format_member_list(filter_bots(idle)), inline=False)
        e.add_field(name=f"\U0001F534 DND ({len(dnd)})", value=self._format_member_list(filter_bots(dnd)), inline=False)
        e.add_field(name=f"\u26AB Offline ({len(offline)})", value=self._format_member_list(filter_bots(offline)), inline=False)
        if warn:
            e.description = warn
        await ctx.send(embed=e)

    # =========================
    # Ping / Roleinfo / Uptime / Joined / Roles / Whois / Stats
    # =========================
    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Get information about a role")
    @app_commands.describe(role="The role to get information about")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(
            title=f"Role Information - {role.name}",
            color=role.color if role.color != discord.Color.default() else discord.Color.blue()
        )
        embed.add_field(name="Role Name", value=role.name, inline=True)
        embed.add_field(name="Role ID", value=role.id, inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        created_at = int(role.created_at.timestamp())
        embed.add_field(name="Created", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        if role.permissions.administrator:
            embed.add_field(name="Permissions", value="Administrator (All permissions)", inline=False)
        else:
            key_perms = []
            perm_checks = [
                ("Kick Members", role.permissions.kick_members),
                ("Ban Members", role.permissions.ban_members),
                ("Manage Messages", role.permissions.manage_messages),
                ("Manage Channels", role.permissions.manage_channels),
                ("Manage Server", role.permissions.manage_guild),
                ("Manage Roles", role.permissions.manage_roles),
                ("Mention Everyone", role.permissions.mention_everyone),
            ]
            for perm_name, has_perm in perm_checks:
                if has_perm:
                    key_perms.append(perm_name)
            if key_perms:
                embed.add_field(name="Key Permissions", value=", ".join(key_perms), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="uptime", description="Show how long the bot has been running")
    async def uptime(self, interaction: discord.Interaction):
        uptime_duration = utcnow() - self.start_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_parts = []
        if days > 0:
            uptime_parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            uptime_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            uptime_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not uptime_parts:
            uptime_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        uptime_text = ", ".join(uptime_parts)
        embed = discord.Embed(
            title="⏱️ Bot Uptime",
            color=discord.Color.green()
        )
        embed.add_field(name="Uptime", value=uptime_text, inline=False)
        embed.add_field(name="Started", value=format_dt(self.start_time, style="F"), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="joined", description="Show when a member joined the server")
    @app_commands.describe(member="The member to check join date for")
    async def joined(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user

        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Join information is only available for server members.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Join Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
        days_since_join = (utcnow() - member.joined_at).days
        embed.add_field(name="Days in Server", value=f"{days_since_join} days", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roles", description="Show all roles in the server or a specific member's roles")
    @app_commands.describe(member="The member to show roles for (optional)")
    async def roles(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member:
            if len(member.roles) <= 1:
                embed = discord.Embed(
                    title=f"{member.display_name}'s Roles",
                    description="This member has no special roles.",
                    color=discord.Color.blue()
                )
            else:
                roles = [role.mention for role in reversed(member.roles[1:])]
                embed = discord.Embed(
                    title=f"{member.display_name}'s Roles",
                    description="\n".join(roles),
                    color=member.color if member.color != discord.Color.default() else discord.Color.blue()
                )
                embed.add_field(name="Role Count", value=len(member.roles) - 1, inline=True)
        else:
            guild_roles = [role for role in reversed(interaction.guild.roles[1:])]
            if not guild_roles:
                embed = discord.Embed(
                    title=f"{interaction.guild.name} Roles",
                    description="This server has no special roles.",
                    color=discord.Color.blue()
                )
            else:
                roles_text = "\n".join([f"{role.mention} - {len(role.members)} members" for role in guild_roles[:20]])
                if len(guild_roles) > 20:
                    roles_text += f"\n... and {len(guild_roles) - 20} more roles"
                embed = discord.Embed(
                    title=f"{interaction.guild.name} Roles",
                    description=roles_text,
                    color=discord.Color.blue()
                )
                embed.add_field(name="Total Roles", value=len(guild_roles), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="whois", description="Detailed information about a user")
    @app_commands.describe(user="The user to get information about")
    async def whois(self, interaction: discord.Interaction, user: discord.User):
        embed = discord.Embed(
            title=f"User Information - {user.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Username", value=f"{user.name}#{user.discriminator}", inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
        if isinstance(user, discord.Member):
            embed.add_field(name="Joined", value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)
            embed.add_field(name="Status", value=user.status.name.title(), inline=True)
            embed.add_field(name="Top Role", value=user.top_role.mention, inline=True)
            embed.add_field(name="Role Count", value=len(user.roles) - 1, inline=True)
            if user.premium_since:
                embed.add_field(name="Boosting Since", value=f"<t:{int(user.premium_since.timestamp())}:F>", inline=False)
        embed.add_field(name="Bot Account", value="Yes" if user.bot else "No", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="Show server statistics")
    async def stats(self, interaction: discord.Interaction):
        guild = interaction.guild

        # Count members by status
        online = sum(1 for member in guild.members if member.status == discord.Status.online)
        idle = sum(1 for member in guild.members if member.status == discord.Status.idle)
        dnd = sum(1 for member in guild.members if member.status == discord.Status.dnd)
        offline = sum(1 for member in guild.members if member.status == discord.Status.offline)

        # Count channels
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        # Count bots vs humans
        bots = sum(1 for member in guild.members if member.bot)
        humans = guild.member_count - bots

        embed = discord.Embed(
            title=f"{guild.name} Statistics",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        embed.add_field(
            name="\U0001F465 Members",
            value=f"Total: {guild.member_count}\nHumans: {humans}\nBots: {bots}",
            inline=True
        )
        embed.add_field(
            name="\U0001F4CA Status",
            value=f"\U0001F7E2 Online: {online}\n\U0001F7E1 Idle: {idle}\n\U0001F534 DND: {dnd}\n\u26AB Offline: {offline}",
            inline=True
        )
        embed.add_field(
            name="\U0001F4CB Channels",
            value=f"Text: {text_channels}\nVoice: {voice_channels}\nCategories: {categories}",
            inline=True
        )
        embed.add_field(name="\U0001F4C5 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=False)
        embed.add_field(name="\U0001F451 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="\U0001F3AD Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="\U0001F600 Emojis", value=len(guild.emojis), inline=True)

        if guild.premium_subscription_count:
            embed.add_field(name="\U0001F48E Boosts", value=f"{guild.premium_subscription_count} (Level {guild.premium_tier})", inline=True)

        await interaction.response.send_message(embed=embed)

    # =========================
    # Prefix command versions (auto-delete where appropriate)
    # =========================
    @commands.command(name="userinfo", aliases=["ui"])
    async def prefix_userinfo(self, ctx, member: Optional[discord.Member] = None):
        await self.delete_command_message(ctx)
        if member is None:
            member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("❌ User information is only available for server members.", delete_after=5)
            return
        embed = discord.Embed(
            title=f"User Information - {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Status", value=member.status.name.title(), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="avatar", aliases=["av"])
    async def prefix_avatar(self, ctx, member: Optional[discord.Member] = None):
        await self.delete_command_message(ctx)
        if member is None:
            member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("❌ Avatar information is only available for server members.", delete_after=5)
            return
        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="ping")
    async def prefix_ping(self, ctx):
        await self.delete_command_message(ctx)
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(UtilityCog(bot))
