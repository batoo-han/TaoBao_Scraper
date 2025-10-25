"""
Core Package
============
Core business logic and configuration.
"""

from .scraper import Scraper
from .config import settings

__all__ = ['Scraper', 'settings']

