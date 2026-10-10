import os
from pathlib import Path

env_file = Path(".env")
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

TEAM_TOKEN: str = os.getenv("TEAM_TOKEN", "")
USER_TOKEN: str = os.getenv("USER_TOKEN", os.getenv("TOKEN", ""))
ORIGINAL_URL: str = os.getenv("ORIGINAL_URL", "https://caja-negra-production-c64f.up.railway.app")
PORT: int = int(os.getenv("PORT", "8000"))
