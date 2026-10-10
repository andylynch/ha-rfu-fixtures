"""Constants for RFU Fixtures & Results."""
from datetime import timedelta

DOMAIN = "rfu_fixtures"
PLATFORMS = ["sensor"]

CONF_URL = "url"
CONF_TEAM = "team"
CONF_COMPETITION = "competition"
CONF_DIVISION = "division"
CONF_SEASON = "season"
CONF_FETCH_GROUP = "fetch_group"

# Polite polling: every 3 hours normally, every 30 minutes on Sunday
# afternoons/evenings when youth results tend to be entered.
INTERVAL_NORMAL = timedelta(hours=3)
INTERVAL_MATCHDAY = timedelta(minutes=30)
MATCHDAY_WEEKDAY = 6  # Sunday
MATCHDAY_HOURS = range(12, 21)

# Pause between page requests when fetching the other teams in the group.
REQUEST_GAP_SECONDS = 3
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1"
)

EVENT_NEW_RESULT = f"{DOMAIN}_new_result"
