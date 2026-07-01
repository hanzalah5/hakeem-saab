"""FemVerse shared library.

This package holds code shared by the per-domain ADK apps (``menstrual/``,
``pregnancy/``, and ``nutrition/``): prompt loader, tools, callbacks, Memory
Bank + Session service factories, settings, and the runner factory.

The apps live at the workspace root (not inside this package) so the ADK CLI
discovers each one as its own ``app_name``. Import from this package; do not
import this package directly as an ADK app.
"""
