"""Count pytest test cases programmatically."""
import sys
sys.path.insert(0, 'D:/TravelMindAgent/backend')

import pytest

# Run collection and count
exit_code = pytest.main(['--collect-only', '-q', '--override-ini=addopts='])
# exit_code contains the count when --collect-only is used
# The count is printed to stdout
