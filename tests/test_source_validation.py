"""Read-only parsing of all Python, shell and systemd units (no execution)."""
import ast
import configparser
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(x in p.parts for x in ('.git', '__pycache__', '.pytest_cache')))
PY_FILES = [p for p in SOURCES if p.suffix == '.py' and '/tests/' not in str(p)]
SH_FILES = [p for p in SOURCES if p.suffix == '.sh' and '/tests/' not in str(p)]
UNITS = [p for p in SOURCES if p.suffix in ('.service', '.timer')]

@pytest.mark.parametrize('path', PY_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_python_parses(path):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

@pytest.mark.parametrize('path', SH_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_shell_parses(path):
    result = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

@pytest.mark.parametrize('path', UNITS, ids=lambda p: str(p.relative_to(ROOT)))
def test_unit_parses(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path)
    assert 'Unit' in parser
    assert ('Service' if path.suffix == '.service' else 'Timer') in parser
