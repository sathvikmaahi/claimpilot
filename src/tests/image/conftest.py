"""pytest setup for the image tests.

Loads the .env so tests that touch Cloud SQL / GCS have credentials at import
time, regardless of how pytest is invoked — the same pattern the voice tests use.
"""

import os
from dotenv import load_dotenv

here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(here, "..", "..", "agents", "narrative_extractor", ".env"))
