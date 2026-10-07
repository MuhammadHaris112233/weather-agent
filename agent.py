"""Daily Weather Intelligence Agent (free version, uses Google Gemini).

The AI model is given three tools (forecast, recent weather, send email) and
decides how to use them to write a short, useful morning briefing.
"""
import os
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests

from common import CITY, TIMEZONE, env, get_weather, read_log, upsert_rows

MODEL = env("MODEL", "gemini-3.1-flash-lite")
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

TOOLS = [{"functionDeclarations": [
    {"name": "get_forecast",
     "description": "Daily forecast starting today: temperatures, rain, chance of rain, wind. days is 1 to 7.",
     "parameters": {"type": "OBJECT",
                    "properties": {"days": {"type": "INTEGER"}},
                    "required": ["days"]}},
    {"name": "get_recent_weather",
     "description": "Observed daily weather for the past N days, ending yesterday. days is 1 to 14.",
     "parameters": {"type": "OBJECT",
                    "properties": {"days": {"type": "INTEGER"}},
                    "required": ["days"]}},
    {"name": "send_email",
     "description": "Send the finished briefing to the user. Call once, at the end.",
     "parameters": {"type": "OBJECT",
                    "properties": {"subject": {"type": "STRING"}, "body": {"type": "STRING"}},
                    "required": ["subject", "body"]}},
]}]

sent = {"subject": None, "body": None}

def call_model(contents):
    """One request to the Gemini API, with a few retries for busy or rate-limited moments."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": contents, "tools": TOOLS}
    for attempt in range(4):
        r = requests.post(url, json=body, timeout=90,
                          headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        if r.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]
    raise RuntimeError("Gemini did not respond.")

def deliver(subject, body):
    if DRY_RUN:
        print(f"--- DRY RUN, not sent ---\nSubject: {subject}\n\n{body}\n")
        return
    to = env("EMAIL_TO", os.getenv("GMAIL_ADDRESS", ""))
    if os.getenv("RESEND_API_KEY"):  # free service, sends over HTTPS (no Gmail login needed)
        r = requests.post("https://api.resend.com/emails", timeout=30,
                          headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]},
                          json={"from": "Weather Agent <onboarding@resend.dev>",
                                "to": [to], "subject": subject, "text": body})
        r.raise_for_status()
        return
    user = os.environ["GMAIL_ADDRESS"].strip()
    pw = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)

def run_tool(name, args):
    if name == "get_forecast":
        return get_weather(past_days=0, forecast_days=max(1, min(7, int(args["days"]))))
    if name == "get_recent_weather":
        return get_weather(past_days=max(1, min(14, int(args["days"]))), forecast_days=1)[:-1]
    if name == "send_email":
        sent.update(subject=args["subject"], body=args["body"])
        deliver(args["subject"], args["body"])
        return {"status": "sent"}
    return {"error": "unknown tool"}

def should_run(today):
    if FORCE or DRY_RUN:
        return True
    if datetime.now(ZoneInfo(TIMEZONE)).hour < SEND_HOUR:
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
    contents = [{"role": "user", "parts": [{"text": f"Today is {today}. Write and send my briefing."}]}]
    reply = {"parts": []}
    for _ in range(8):
        reply = call_model(contents)
        contents.append(reply)  # sent back unchanged so the model keeps its context
        calls = [p["functionCall"] for p in reply.get("parts", []) if "functionCall" in p]
        if not calls:
            break
        results = [{"functionResponse": {"name": c["name"],
                                         "response": {"result": run_tool(c["name"], c.get("args", {}))}}}
                   for c in calls]
        contents.append({"role": "user", "parts": results})
    if not sent["body"]:  # safety net if the model replied with text and skipped the tool
        text = "".join(p.get("text", "") for p in reply.get("parts", [])).strip()
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
