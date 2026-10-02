SETUP CHECKLIST (about 30 minutes, nothing to code)

Default city is Belfast and the email goes out around 7am UK time.
To change the city, see step 5.

1. GITHUB REPO
   - Create a free account at github.com, then a new PUBLIC repository
     called weather-agent (public is needed for the free dashboard and Power BI link).
   - Unzip the kit. On the repo page choose Add file > Upload files and
     drag in everything from the unzipped folder, including the .github folder.
     Commit.

2. ANTHROPIC API KEY (the AI brain)
   - console.anthropic.com > sign up > add a small amount of credit (5 dollars is plenty)
   - API keys > Create key. Copy it. One daily briefing should cost very little.

3. GMAIL APP PASSWORD (lets the agent send email)
   - Turn on 2-Step Verification on your Google account.
   - Go to myaccount.google.com/apppasswords, create one called weather-agent,
     copy the 16 character code.

4. GITHUB SECRETS
   - Repo > Settings > Secrets and variables > Actions > New repository secret
   - Add: ANTHROPIC_API_KEY, GMAIL_ADDRESS (your Gmail), GMAIL_APP_PASSWORD
   - Optional: EMAIL_TO if you want it sent to a different address.
   - Also check Settings > Actions > General > Workflow permissions is set to
     Read and write.

5. CITY (optional)
   - Same page, Variables tab, add CITY (for example Belfast). To use another
     city also add LAT and LON (look them up on latlong.net).

6. LOAD THE LAST 30 DAYS
   - Actions tab > Backfill last 30 days > Run workflow. This fills the dashboard
     with real data straight away.

7. TEST THE EMAIL
   - Actions tab > Daily weather briefing > Run workflow. Within a minute or two
     the briefing should land in your inbox. After that it runs by itself every morning.

8. LIVE DASHBOARD
   - share.streamlit.io > sign in with GitHub > New app > pick your repo,
     branch main, main file dashboard.py > Deploy. Copy the link for your portfolio.

9. POWER BI
   - Power BI Desktop > Get data > Web, paste:
     https://raw.githubusercontent.com/YOUR-USERNAME/weather-agent/main/data/weather_log.csv
   - Use Transform data to set date as Date, the number columns as Decimal.
   - Add the measures from powerbi_measures.dax.txt, build cards, a line chart of
     highs and lows, a rainfall column chart, and a table with the briefing column.
   - Publish needs a work or school account. Without one, save screenshots and
     keep the Streamlit link as your main live demo.

IF SOMETHING GOES WRONG
   - Open the failed run in the Actions tab and read the red line. Paste it to me.
   - Common ones: wrong Gmail app password, no API credit, or Workflow permissions
     not set to Read and write.
