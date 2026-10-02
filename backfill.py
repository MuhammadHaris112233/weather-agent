"""Run once. Fills the log with the last 30 days of real weather so the dashboard has data on day one."""
from common import CITY, get_weather, upsert_rows

days = get_weather(past_days=30, forecast_days=1)
upsert_rows([{**d, "city": CITY, "briefing": ""} for d in days])
print(f"Added {len(days)} days for {CITY}.")
