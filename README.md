# Daily Weather Intelligence Agent

An AI agent that checks the weather every morning, compares it with recent days,
writes a short personal briefing and emails it to me. A live dashboard and a
Power BI report read from the same daily log.

## How it works

    GitHub Actions (daily schedule)
            |
            v
    agent.py  --->  Claude (tool use)  --->  Open-Meteo API (forecast, history)
            |                 |
            |                 +--->  send_email tool  --->  Gmail
            v
    data/weather_log.csv  (committed back to the repo each day)
            |
            +--->  Streamlit dashboard (live link)
            +--->  Power BI report (Web connector)

## Why it is an agent and not just a script

A script runs fixed steps. Here Claude gets three tools (get forecast, get recent
weather, send email) and decides which to call and what to say. The briefing
changes with the weather, for example it flags a big temperature drop or the
best dry window instead of repeating a template.

## Stack

Python, Claude API (tool use), Open-Meteo, Gmail SMTP, GitHub Actions,
pandas, Streamlit, Power BI (DAX).

## Run it yourself

See SETUP.md. To try it without sending email, set DRY_RUN=1 and run
`python agent.py` with an ANTHROPIC_API_KEY set.

## Design choices

- The send hour is checked in UK local time so daylight saving does not shift the email.
- Re-runs on the same day are skipped so you never get two emails.
- The log is a plain CSV in the repo, so there is no database to maintain.
- Weather data is free and needs no key.

## Possible next steps

Rain alerts through the day, several cities, a Telegram message instead of email,
and comparing forecast accuracy against what actually happened.
