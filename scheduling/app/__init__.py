"""BT Openreach Scheduling Copilot application package.

Loads environment variables from a ``.env`` file at import time so that
``os.getenv`` works regardless of which entry point (CLI or MCP server)
is started, and regardless of whether the operator remembered to export
the variables in their shell.

``load_dotenv()`` searches from the current working directory upward,
so a ``.env`` at the repo root is picked up when commands are run from
either the repo root or the ``scheduling/`` subfolder. Missing file is
a silent no-op.
"""

from dotenv import load_dotenv

load_dotenv()
