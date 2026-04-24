import os

BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
IVASMS_EMAIL = os.environ.get('IVASMS_EMAIL')
IVASMS_PASSWORD = os.environ.get('IVASMS_PASSWORD')
GROUP_ID = int(os.environ.get('GROUP_ID', 0))
AUTO_REFRESH_INTERVAL = int(os.environ.get('AUTO_REFRESH', 10800))

COUNTRIES = {
    "Pakistan": "+92",
    "Bangladesh": "+880",
    "Indonesia": "+62",
    "icovey coast": "225",
}
