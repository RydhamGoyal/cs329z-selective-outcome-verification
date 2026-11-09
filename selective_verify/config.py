"""Load credentials from this project's private environment file."""
from pathlib import Path
from dotenv import load_dotenv

def load_project_env(path: Path | None = None) -> bool:
    """Load .env explicitly; tau2's implicit lookup starts in its own package."""
    target = path or Path(__file__).resolve().parents[1] / '.env'
    return load_dotenv(target)
