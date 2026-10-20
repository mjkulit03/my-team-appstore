"""Simulated AI employee agents.

Each agent is a pure function: plain input, plain dict output, no network calls
and no API keys. The FastAPI layer in ``main.py`` is a thin wrapper around these.
"""

from .accounting import run_accounting_agent
from .marketing import run_marketing_agent
from .sales import run_sales_agent

__all__ = [
    "run_marketing_agent",
    "run_sales_agent",
    "run_accounting_agent",
]