"""Print which voice keys are set and which are still missing.

    .venv/bin/python -m voice.check
"""
from .config import checklist

if __name__ == "__main__":
    print(checklist())
