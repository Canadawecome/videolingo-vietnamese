"""Vietnamese faithful-translation edition; the English entrypoint stays intact."""
from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).resolve().with_name('upgrade_app.py')),
               init_globals={'APP_EDITION': 'vi'})
