import pytest
from src.memory.core import CoreMemory

def test_get_context():
    memory = CoreMemory()
    result = memory.get_context()
    assert result == "Core Context"
