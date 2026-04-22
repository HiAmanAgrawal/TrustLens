"""Cross-cutting infrastructure: settings, logging, etc.

These modules are imported widely, so they must stay light and never import
from ``app.api`` or ``app.services`` (avoids circular imports).
"""
