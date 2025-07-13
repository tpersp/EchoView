import pytest
import importlib

@pytest.mark.parametrize("module", ["echoview", "app", "config", "utils"])
def test_imports(module):
    pytest.importorskip("requests", reason="optional dependency")
    importlib.import_module(module)
