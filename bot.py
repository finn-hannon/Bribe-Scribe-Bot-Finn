import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

client = OpenAI()

SYSTEM_PROMPT_CACHE = ""
LEAGUE_DATA_CACHE = ""

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

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

from openai import RateLimitError, APIError, APIConnectionError

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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

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

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing in .env")
    bot.run(DISCORD_TOKEN)