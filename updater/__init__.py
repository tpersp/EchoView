"""Updater package.

Contains the logic used to update this application from GitHub.
"""

from .update import perform_update

__all__ = ["perform_update"]
