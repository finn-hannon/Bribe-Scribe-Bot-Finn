import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError, APIConnectionError
from economy import init_db, get_balance, get_recent_transactions, claim_daily, transfer, top_balances, grant, set_balance

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
SYSTEM_PROMPT_CACHE = ""
LEAGUE_DATA_CACHE = ""
client = OpenAI()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
WARPSTONE_EMOJI = "<:BBBroadcastWarpstone:1470902120223084678>"


def load_system_prompt() -> str:
    global SYSTEM_PROMPT_CACHE
    if not SYSTEM_PROMPT_CACHE:
        try:
            with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
                SYSTEM_PROMPT_CACHE = f.read().strip()
        except FileNotFoundError:
            SYSTEM_PROMPT_CACHE = "You are The Bribe Scribe."
    return SYSTEM_PROMPT_CACHE

def load_league_data() -> str:
    global LEAGUE_DATA_CACHE
    if not LEAGUE_DATA_CACHE:
        try:
            with open("league_data.txt", "r", encoding="utf-8") as f:
                LEAGUE_DATA_CACHE = f.read().strip()
        except FileNotFoundError:
            LEAGUE_DATA_CACHE = ""
    return LEAGUE_DATA_CACHE

def is_admin(ctx) -> bool:
    return ctx.author.guild_permissions.administrator

def ws(amount: int) -> str:
    return f"{amount} {WARPSTONE_EMOJI}"

def generate_text(user_prompt: str) -> str:
    try:
        system_prompt = load_system_prompt()
        league_data = load_league_data()

        full_prompt = system_prompt.strip()
        if league_data:
            full_prompt += "\n\nLEAGUE DATA (authoritative, do not contradict):\n" + league_data.strip()
        full_prompt += "\n\nREQUEST:\n" + user_prompt.strip()

        resp = client.responses.create(
            model="gpt-5-mini",
            input=full_prompt,
        )

        text = resp.output_text.strip()
        return text.replace("@everyone", "everyone").replace("@here", "here")
    except RateLimitError:
        return ("The Bribe Scribe is temporarily out of ink and coin. "
                "Try again later once the bookmakers have topped up the purse.")
    except (APIConnectionError, APIError):
        return ("The Bribe Scribe cannot reach the wire right now. "
                "Try again in a moment.")
    except Exception:
        return ("The Bribe Scribe had an… incident. Try again shortly.")

##
## Initialisation below
##

@bot.event
async def on_ready():
    print("on_ready fired, initialising DB...")
    init_db()
    print("DB init complete")
    print("Commands loaded:", [c.name for c in bot.commands])
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

@bot.command()
async def rumour(ctx):
    prompt = (
    "Generate ONE Bribe Scribe rumour grounded in LEAGUE DATA. "
    "Pick a random team/coach/player from LEAGUE DATA and centre the rumour on them. "
    "Choose a scandal angle that is NOT the same as your last output (discipline, ref drama, warpstone market, sponsorship, training bust-up, contract dispute, injury gossip). "
    "Include a short 'on-pitch impact' line. "
    "Output format: choose one of the rotation formats described in the system prompt."
    )   
    await ctx.send(generate_text(prompt))

@bot.command()
async def odds(ctx, *, matchup: str = ""):
    if matchup:
        prompt = (
    f"Create odds for {matchup} using only teams in LEAGUE DATA. "
    "Output:\n"
    "- MONEYLINE: Team A (x.xx) | Team B (x.xx)\n"
    "- 2 PROPS tied to factions/playstyle (x.xx)\n"
    "- One sentence explaining why the line looks like that (injuries, form, coaching, corruption hint). "
    "Keep it concise."
    )
    else:
        prompt = (
    "Post odds for each fixture in Round 2 Fixtures from LEAGUE DATA. "
    "For each fixture provide:\n"
    "- MONEYLINE in decimal odds\n"
    "- 1 PROP\n"
    "Keep each fixture to two lines max. "
    "Add one brief 'market note' at the end about odds movement or suspicious money."
    )   
    await ctx.send(generate_text(prompt))

@bot.command()
async def bank(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"{ctx.author.display_name} has {ws(bal)}")

@bot.command()
async def statement(ctx, n: int = 5):
    rows = get_recent_transactions(ctx.author.id, limit=max(1, min(n, 10)))

    if not rows:
        await ctx.send("No transactions yet.")
        return

    lines = [f"Recent Warp Stone transactions for {ctx.author.display_name}:"]
    for r in rows:
        lines.append(f'{r["tx_id"]}: {r["amount"]:+d} ({r["reason"]})')

    await ctx.send("\n".join(lines))

@bot.command()
async def daily(ctx):
    ok, msg, new_balance, remaining = claim_daily(ctx.author.id)

    if ok:
        await ctx.send(
            f"{msg} Your sponsors wired +{150} Warp Stones. "
            f"You now have {new_balance} Warp Stones."
        )
    else:
        # remaining is in seconds
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await ctx.send(f"{msg} Next payout in {hours}h {minutes}m.")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    # Basic guardrails
    if member.bot:
        await ctx.send("Bots do not accept Warp Stones.")
        return

    if member.id == ctx.author.id:
        await ctx.send("Paying yourself is not money laundering, it is just confusing.")
        return

    ok, msg = transfer(ctx.author.id, member.id, amount)

    if ok:
        await ctx.send(
            f"{ctx.author.display_name} paid {member.display_name} {amount} Warp Stones."
        )
    else:
        await ctx.send(msg)

@bot.command()
async def leaderboard(ctx):
    rows = top_balances(limit=10)
    if not rows:
        await ctx.send("The bookies have no accounts on record yet.")
        return

    lines = ["Top bookie credit lines (Warp Stones):"]
    for i, r in enumerate(rows, start=1):
        user_id = int(r["user_id"])

        member = ctx.guild.get_member(user_id)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(user_id)
            except Exception:
                member = None

        name = member.display_name if member else f"User {user_id}"
        balance = int(r["balance"])
        lines.append(f"{i}) {name}: {ws(balance)}")

    await ctx.send("\n".join(lines))

@bot.command()
async def grantwarp(ctx, member: discord.Member, amount: int):
    if not is_admin(ctx):
        await ctx.send("Nice try. Only the Commissioner and accredited bookies can mint stones.")
        return
    if member.bot:
        await ctx.send("Bots do not accept Warp Stones.")
        return

    ok, msg, new_bal = grant(member.id, amount, reason=f"admin_grant_by:{ctx.author.id}")
    if ok:
        await ctx.send(f"Ledger updated. {member.display_name} now has {ws(new_bal)} ")
    else:
        await ctx.send(msg)

@bot.command()
async def setwarp(ctx, member: discord.Member, new_balance: int):
    if not is_admin(ctx):
        await ctx.send("Only the Commissioner can rewrite the ledger.")
        return
    if member.bot:
        await ctx.send("Bots do not accept Warp Stones.")
        return

    ok, msg, final_bal, delta = set_balance(member.id, new_balance, reason=f"admin_set_by:{ctx.author.id}")
    if ok:
        sign = "+" if delta >= 0 else ""
        await ctx.send(f"Ledger rewritten. {member.display_name} set to {ws(final_bal)} ({sign}{delta}).")
    else:
        await ctx.send(msg)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing in .env")
    bot.run(DISCORD_TOKEN)

