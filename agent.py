
"""Daily Weather Intelligence Agent using Google Gemini.

Retrieves weather data, generates a personalised briefing, sends email,
and maintains a weather log and delivery record.
"""

import json
import os
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from common import CITY, TIMEZONE, env, get_weather, read_log, upsert_rows


MODEL = env("MODEL", "gemini-3.1-flash-lite")
SEND_HOUR = int(env("SEND_HOUR", "7"))
DRY_RUN = env("DRY_RUN", "0") == "1"
FORCE = env("FORCE_RUN", "0") == "1"

DELIVERY_PATH = Path(
    env("DELIVERY_PATH", "data/email_delivery.json")
)

SYSTEM = f"""You are a friendly personal weather assistant for someone in {CITY}.
Write a short morning briefing (under 150 words) in plain, natural English.
Do not use em dashes, long bullet lists, or marketing language.
Look at today's forecast and recent weather.
Explain what to wear or bring, how today compares with yesterday,
and mention the next two days briefly.
Use Celsius and km/h.
Finish by calling send_email exactly once.
"""

TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "get_forecast",
                "description": "Daily weather forecast for 1 to 7 days.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "days": {"type": "INTEGER"}
                    },
                    "required": ["days"]
                }
            },
            {
                "name": "get_recent_weather",
                "description": "Recent weather for 1 to 14 days, ending yesterday.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "days": {"type": "INTEGER"}
                    },
                    "required": ["days"]
                }
            },
            {
                "name": "send_email",
                "description": "Send the finished weather briefing once.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "subject": {"type": "STRING"},
                        "body": {"type": "STRING"}
                    },
                    "required": ["subject", "body"]
                }
            }
        ]
    }
]

sent = {"subject": None, "body": None}


def local_today():
    return datetime.now(
        ZoneInfo(TIMEZONE)
    ).strftime("%Y-%m-%d")


def read_delivery_record():
    try:
        with DELIVERY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_delivery_record(record):
    DELIVERY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_path = DELIVERY_PATH.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    temp_path.replace(DELIVERY_PATH)


def already_sent(today):
    record = read_delivery_record()
    key = f"{CITY}:{today}"

    return record.get(key, {}).get("status") == "sent"


def mark_sent(today, subject):
    record = read_delivery_record()
    key = f"{CITY}:{today}"

    record[key] = {
        "status": "sent",
        "subject": subject,
        "timestamp": datetime.now(
            ZoneInfo(TIMEZONE)
        ).isoformat()
    }

    save_delivery_record(record)


def call_model(contents):
    """Call Gemini with retries for temporary API failures."""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{MODEL}:generateContent"
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM}]
        },
        "contents": contents,
        "tools": TOOLS
    }

    for attempt in range(4):
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=(10, 90),
                headers={
                    "x-goog-api-key": os.environ["GEMINI_API_KEY"]
                }
            )

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue

            response.raise_for_status()

            return response.json()["candidates"][0]["content"]

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError):

            if attempt == 3:
                raise

            time.sleep(10 * (attempt + 1))

    raise RuntimeError("Gemini did not respond.")


def deliver(subject, body, today):
    """Send one email and record successful delivery submission."""

    if sent["body"] is not None:
        print("Email already processed in this run.")
        return {"status": "already_processed"}

    if not FORCE and already_sent(today):
        print("Email already recorded as sent today.")
        return {"status": "already_sent"}

    if DRY_RUN:
        print(
            f"--- DRY RUN ---\n"
            f"Subject: {subject}\n\n{body}\n"
        )
        sent.update(subject=subject, body=body)
        return {"status": "dry_run"}

    recipient = env(
        "EMAIL_TO",
        os.getenv("GMAIL_ADDRESS", "")
    )

    if not recipient:
        raise RuntimeError("EMAIL_TO is not configured.")

    if os.getenv("RESEND_API_KEY"):
        response = requests.post(
            "https://api.resend.com/emails",
            timeout=(10, 30),
            headers={
                "Authorization": (
                    "Bearer " + os.environ["RESEND_API_KEY"]
                )
            },
            json={
                "from": "Weather Agent <onboarding@resend.dev>",
                "to": [recipient],
                "subject": subject,
                "text": body
            }
        )

        response.raise_for_status()

    else:
        user = os.environ["GMAIL_ADDRESS"].strip()
        password = os.environ[
            "GMAIL_APP_PASSWORD"
        ].replace(" ", "").strip()

        message = EmailMessage()
        message["From"] = user
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=30
        ) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)

    sent.update(subject=subject, body=body)
    mark_sent(today, subject)

    print("Email submitted successfully.", flush=True)

    return {"status": "sent"}


def run_tool(name, args, today):
    if name == "get_forecast":
        days = max(1, min(7, int(args.get("days", 3))))

        return get_weather(
            past_days=0,
            forecast_days=days
        )

    if name == "get_recent_weather":
        days = max(1, min(14, int(args.get("days", 3))))

        return get_weather(
            past_days=days,
            forecast_days=1
        )[:-1]

    if name == "send_email":
        return deliver(
            args["subject"],
            args["body"],
            today
        )

    return {"error": "Unknown tool"}


def should_run(today):
    if not FORCE and not DRY_RUN:
        hour = datetime.now(
            ZoneInfo(TIMEZONE)
        ).hour

        if hour < SEND_HOUR:
            print("Too early in Belfast. Skipping.")
            return False

    if not FORCE and already_sent(today):
        print("Today's email was already sent. Skipping.")
        return False

    return True


def main():
    today = local_today()

    if not should_run(today):
        return

    # Fetch today's weather BEFORE sending the email.
    # This prevents a late weather API failure after delivery.
    todays = [
        d for d in get_weather(0, 1)
        if d["date"] == today
    ]

    if not todays:
        raise RuntimeError(
            "Today's weather data was not returned."
        )

    # Save weather information before sending the email.
    # Preserve any existing briefing in the CSV.
    upsert_rows([
        {
            **todays[0],
            "city": CITY,
            "briefing": ""
        }
    ])

    contents = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        f"Today is "
                        f"{datetime.now(ZoneInfo(TIMEZONE)):%A %d %B %Y}. "
                        "Write and send my briefing."
                    )
                }
            ]
        }
    ]

    reply = {"parts": []}

    for _ in range(8):
        reply = call_model(contents)
        contents.append(reply)

        calls = [
            part["functionCall"]
            for part in reply.get("parts", [])
            if "functionCall" in part
        ]

        if not calls:
            break

        results = []

        for call in calls:
            result = run_tool(
                call["name"],
                call.get("args", {}),
                today
            )

            results.append({
                "functionResponse": {
                    "name": call["name"],
                    "response": {"result": result}
                }
            })

        contents.append({
            "role": "user",
            "parts": results
        })

        # Stop after email submission.
        if sent["body"] is not None:
            break

    # Fallback if Gemini produces text without calling send_email.
    if sent["body"] is None:
        text = "".join(
            part.get("text", "")
            for part in reply.get("parts", [])
        ).strip()

        if text:
            deliver(
                f"Weather in {CITY} today",
                text,
                today
            )

    if sent["body"] is None:
        sys.exit("The agent did not produce a briefing.")

    # Save the AI briefing to the same CSV used by dashboards.
    upsert_rows([
        {
            **todays[0],
            "city": CITY,
            "briefing": sent["body"]
        }
    ])

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
