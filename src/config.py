import os

TEAM_TOKEN: str = os.getenv("TEAM_TOKEN", "")
ORIGINAL_URL: str = os.getenv("ORIGINAL_URL", "https://caja-negra-production-c64f.up.railway.app")
PORT: int = int(os.getenv("PORT", "8000"))
