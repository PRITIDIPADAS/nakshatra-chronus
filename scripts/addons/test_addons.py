"""Run add-on tests without modifying a CHRONOS checkout."""
from pathlib import Path
import sys,pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
raise SystemExit(pytest.main([str(ROOT/"tests"),"-q"]))
