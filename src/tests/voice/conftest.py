"""pytest shared setup — loaded automatically before any test.

Loads the .env so tests that touch Cloud SQL have credentials, regardless of
how pytest is invoked. Without this, modules that read env vars at import time
fail during collection.
"""

import os
from dotenv import load_dotenv

here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(here, "..", "..", "agents", "narrative_extractor", ".env"))
