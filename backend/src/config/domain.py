import json
from pathlib import Path
DOMAIN=json.loads((Path(__file__).parents[1]/'constants/domain.json').read_text())
