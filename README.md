# Bribe Scribe (MVP)

Discord bot for a Blood Bowl league. Generates in-universe rumours and betting odds grounded in league data.

## Setup
1. Create a virtual environment: `py -m venv .venv`
2. Activate it: `.\.venv\Scripts\Activate.ps1`
3. Install deps: `python -m pip install -r requirements.txt`
4. Create a `.env` file with:
   - DISCORD_TOKEN=
   - OPENAI_API_KEY=
5. Run: `python bot.py`

## League data
Edit `league_data.txt` to reflect current teams, fixtures, standings.