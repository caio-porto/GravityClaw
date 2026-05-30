import sys
from unittest.mock import MagicMock

# Mock src.memory module to prevent ImportError during test collection
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()

# Mock CoreMemory and DailyBuffer classes
class MockCoreMemory:
    pass

class MockDailyBuffer:
    pass

sys.modules['src.memory.core'].CoreMemory = MockCoreMemory
sys.modules['src.memory.buffer'].DailyBuffer = MockDailyBuffer
