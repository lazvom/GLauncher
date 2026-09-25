import json
import os

# If you've registered your own Azure app for Microsoft sign-in (see the
# README for the one-time setup steps), paste its Client ID here so you
# don't have to enter it in the UI at all. Leave this blank to be prompted
# for it in-app the first time instead - either way, this should only ever
# be an app you registered yourself, never someone else's.
DEFAULT_AZURE_CLIENT_ID = "253275a3-8bab-44c0-a095-e740b065f2c6"


class Settings:
    """The launcher's local config file (settings.json in the data directory).
    Everything here is a per-machine preference you set yourself - nothing
    here ships with a default value baked into the source except whatever
    you optionally put in DEFAULT_AZURE_CLIENT_ID above.

    The Azure Client ID is deliberately NOT saved to settings.json: it lives
    only in source (DEFAULT_AZURE_CLIENT_ID) so the data directory never
    contains it."""

    def __init__(self, base_dir: str):
        self.path = os.path.join(base_dir, "settings.json")
        self.ram_min_mb = 1024
        self.ram_max_mb = 4096
        self.java_path = ""
        self.azure_client_id = DEFAULT_AZURE_CLIENT_ID
        self.console_minimized = False
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.ram_min_mb = d.get("ram_min_mb", self.ram_min_mb)
                self.ram_max_mb = d.get("ram_max_mb", self.ram_max_mb)
                self.java_path = d.get("java_path", self.java_path)
                self.console_minimized = d.get("console_minimized", self.console_minimized)
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ram_min_mb": self.ram_min_mb,
                    "ram_max_mb": self.ram_max_mb,
                    "java_path": self.java_path,
                    "console_minimized": self.console_minimized,
                },
                f, indent=2,
            )
