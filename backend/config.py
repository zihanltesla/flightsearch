"""配置加载：环境变量 + 可选的 backend/.env 文件。"""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载器（不覆盖已有环境变量）。"""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path(__file__).resolve().parent / ".env")

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")

# test = Amadeus 免费测试环境；production = 已审核通过的生产环境
AMADEUS_ENV = os.getenv("AMADEUS_ENV", "test").strip().lower()
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "").strip()
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
APP_VERSION = "0.1.0"


def amadeus_configured() -> bool:
    return bool(AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET)
