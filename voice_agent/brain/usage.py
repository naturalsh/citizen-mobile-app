"""Show how many Gemini requests count towards the spending limit (brain/budget.py).

    .venv/bin/python -m brain.usage
"""
from dotenv import load_dotenv

load_dotenv()  # before importing the brain, so the limits from .env apply

from brain import budget  # noqa: E402

s = budget.status()
print(f"Gemini requests: {s['hour']}/{s['max_per_hour']} in the last hour, {s['day']}/{s['max_per_day']} in the last day")
print("LIMIT ACTIVE: the brain is not calling Gemini, callers go to an operator" if s["limit_on"] else "Limit not active")
