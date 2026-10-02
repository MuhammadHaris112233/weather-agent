"""Daily Weather Intelligence Agent.

Claude is given three tools (forecast, recent weather, send email) and decides
how to use them to write a short, useful morning briefing.
"""
import json
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import anthropic

from common import CITY, TIMEZONE, env, get_weather, read_log, upsert_rows

MODEL = env("MODEL", "claude-sonnet-5-5")
SEND_HOUR = int(env("SEND_HOUR", "7"))
DRY_RUN = env("DRY_RUN", "0") == "1"
FORCE = env("FORCE_RUN", "0") == "1"

SYSTEM = f"""You are a friendly personal weather assistant for someone in {CITY}.
Write a short morning briefing (under 150 words) in plain, natural, spoken-style English.
Do not use em dashes, bullet-point walls, or marketing language.
Use your tools: look at today's forecast and the last few days, then say what matters:
what to wear or bring, the best time to be outside, and how today compares with yesterday.
Mention the next two days in one sentence. Finish by calling send_email exactly once.
Use Celsius and km/h."""

TOOLS = [
    {"name": "get_forecast",
     "description": "Daily forecast starting today: temperatures, rain, chance of rain, wind.",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer", "minimum": 1, "maximum": 7}}, "required": ["days"]}},
    {"name": "get_recent_weather",
     "description": "Observed daily weather for the past N days, ending yesterday.",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer", "minimum": 1, "maximum": 14}}, "required": ["days"]}},
    {"name": "send_email",
     "description": "Send the finished briefing to the user. Call once, at the end.",
     "input_schema": {"type": "object", "properties": {
         "subject": {"type": "string"}, "body": {"type": "string"}},
         "required": ["subject", "body"]}},
]

sent = {"subject": None, "body": None}

def deliver(subject, body):
    if DRY_RUN:
        print(f"--- DRY RUN, not sent ---\nSubject: {subject}\n\n{body}\n")
        return
    user, pw = os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, env("EMAIL_TO", user), subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)

def run_tool(name, args):
    if name == "get_forecast":
        return get_weather(past_days=0, forecast_days=args["days"])
    if name == "get_recent_weather":
        return get_weather(past_days=args["days"], forecast_days=1)[:-1]
    if name == "send_email":
        sent.update(subject=args["subject"], body=args["body"])
        deliver(args["subject"], args["body"])
        return {"status": "sent"}
    return {"error": "unknown tool"}

def should_run(today):
    if FORCE or DRY_RUN:
        return True
    if datetime.now(ZoneInfo(TIMEZONE)).hour != SEND_HOUR:
        print("Not the send hour in local time, skipping.")
        return False
    done = [r for r in read_log() if r["date"] == today and r["city"] == CITY and r["briefing"]]
    if done:
        print("Already sent today, skipping.")
        return False
    return True

def main():
    today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    if not should_run(today):
        return
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": f"Today is {today}. Write and send my briefing."}]
    for _ in range(8):
        resp = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM,
                                      tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            break
        results = [{"type": "tool_result", "tool_use_id": c.id,
                    "content": json.dumps(run_tool(c.name, c.input))} for c in calls]
        messages.append({"role": "user", "content": results})
    if not sent["body"]:  # safety net if the model replied without calling the tool
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text:
            sent.update(subject=f"Weather in {CITY} today", body=text)
            deliver(sent["subject"], text)
    if not sent["body"]:
        sys.exit("The agent did not produce a briefing.")
    todays = [d for d in get_weather(0, 1) if d["date"] == today]
    if todays:
        upsert_rows([{**todays[0], "city": CITY, "briefing": sent["body"]}])
    print("Done.")

if __name__ == "__main__":
    main()
