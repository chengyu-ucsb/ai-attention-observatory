"""Isolate evidence, dating, and headline integration tests from cover production."""
from unittest.mock import patch

import build_public


def article_covers_ready():
    """Supply the post-art selection in tests that exercise upstream eligibility."""
    return patch.object(build_public, "attach_art", side_effect=lambda records, **kwargs: records)
