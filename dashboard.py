"""Streamlit dashboard. Run locally: streamlit run dashboard.py"""
import pandas as pd
import requests
import streamlit as st
from common import CITY, LAT, LON, LOG_PATH, TIMEZONE

st.set_page_config(page_title="Weather Intelligence Agent", page_icon="🌦️", layout="wide")
st.title(f"🌦️ Weather Intelligence Agent: {CITY}")
st.caption("An AI agent writes and emails a briefing every morning. This page reads its daily log.")

@st.cache_data(ttl=600)
def current():
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
        "latitude": LAT, "longitude": LON, "timezone": TIMEZONE,
        "current": "temperature_2m,wind_speed_10m,precipitation"})
    return r.json()["current"]

try:
    c = current()
    a, b, d = st.columns(3)
    a.metric("Right now", f"{c['temperature_2m']} °C")
    b.metric("Wind", f"{c['wind_speed_10m']} km/h")
    d.metric("Rain (current hour)", f"{c['precipitation']} mm")
except Exception:
    st.info("Live conditions are unavailable right now.")

df = pd.read_csv(LOG_PATH, parse_dates=["date"])
if df.empty:
    st.warning("No data yet. Run backfill.py or wait for the first daily run.")
    st.stop()

days = st.sidebar.slider("Days to show", 7, max(len(df), 8), min(30, len(df)))
view = df.sort_values("date").tail(days).set_index("date")

k = st.columns(4)
k[0].metric("Avg high", f"{view.temp_max_c.mean():.1f} °C")
k[1].metric("Avg low", f"{view.temp_min_c.mean():.1f} °C")
k[2].metric("Total rain", f"{view.rain_mm.sum():.1f} mm")
k[3].metric("Rainy days", int((view.rain_mm >= 1).sum()))

l, r = st.columns(2)
l.subheader("Temperature (°C)")
l.line_chart(view[["temp_max_c", "temp_min_c"]])
r.subheader("Rainfall (mm)")
r.bar_chart(view["rain_mm"])

st.subheader("Latest briefing the agent emailed")
sent = df[df.briefing.fillna("") != ""].sort_values("date")
if sent.empty:
    st.write("No briefings yet.")
else:
    last = sent.iloc[-1]
    st.caption(last.date.strftime("%A %d %B %Y"))
    st.write(last.briefing)
