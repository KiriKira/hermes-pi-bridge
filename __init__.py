"""Hermes pi-bridge plugin entrypoint.

Implementation lives in the ``plugin`` package so the repository can remain
organized while also being directly installable with ``hermes plugins install``.
"""

from .plugin import register

__all__ = ["register"]
