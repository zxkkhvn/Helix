import os
from pathlib import Path

# Path to the Helix workspace root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE_PATH = BASE_DIR / "Documents" / "config.cfg"

class Settings:
    """Application configuration and environment variables."""
    def __init__(self):
        self.google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.debug_mode = os.environ.get("DEBUG_MODE", "false").lower() == "true"
        
        # Routing map: Maps task types to model providers
        self.task_routing = {
            "chat": "gemini",
            "formulation": "gemini",
            "local_test": "ollama",
            "default": "gemini"
        }
        self._load_from_cfg()

    def _load_from_cfg(self):
        """Loads simple key=value pairs from config.cfg, ignoring sections."""
        if not CONFIG_FILE_PATH.exists():
            return
            
        with open(CONFIG_FILE_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('['):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key in ("GOOGLE_API_KEY", "API_KEY", "GEMINI_API_KEY_2"):
                        self.google_api_key = val
                    elif key == "OLLAMA_BASE_URL":
                        self.ollama_base_url = val
                    elif key == "DEBUG_MODE":
                        self.debug_mode = val.lower() == "true"

settings = Settings()
