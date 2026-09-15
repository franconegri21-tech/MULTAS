import os
from dotenv import load_dotenv

load_dotenv()

TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "500"))
TIMEOUT = int(os.getenv("TIMEOUT", "30000"))
