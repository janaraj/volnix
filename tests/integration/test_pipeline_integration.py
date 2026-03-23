"""Placeholder for future full-pipeline integration coverage.

Active integration coverage currently lives in the wire, governance, and
gateway/report suites. This module is explicitly skipped so it does not
masquerade as implemented coverage.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Full pipeline integration scenarios are not implemented in this module yet."
)
