import json
import os

# If you've registered your own Azure app for Microsoft sign-in (see the
# README for the one-time setup steps), paste its Client ID here so you
# don't have to enter it in the UI at all. Leave this blank to be prompted
# for it in-app the first time instead - either way, this should only ever
# be an app you registered yourself, never someone else's.
DEFAULT_AZURE_CLIENT_ID = "253275a3-8bab-44c0-a095-e740b065f2c6"

# Kept in one place and validated against on load/save so a corrupted or
# hand-edited settings.json can't smuggle an arbitrary string into the page's
# data-theme attribute (see api.set_theme). The web/style.css side must define
# a matching [data-theme="..."] block for each id here.
THEMES = ("aurora", "nebula", "emerald", "crimson", "mono")
DEFAULT_THEME = "aurora"


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
        self.launch_arguments = ""
        self.azure_client_id = DEFAULT_AZURE_CLIENT_ID
        self.console_minimized = False
        self.theme = DEFAULT_THEME
        # Only a brand-new data directory (no settings.json yet at all) counts
        # as a first run - an existing settings.json with no "onboarded" key
        # means someone updated from a version that predates this feature,
        # not a new player, so they shouldn't see the intro screen either.
        self.onboarded = os.path.exists(self.path)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.ram_min_mb = d.get("ram_min_mb", self.ram_min_mb)
                self.ram_max_mb = d.get("ram_max_mb", self.ram_max_mb)
                self.java_path = d.get("java_path", self.java_path)
                self.launch_arguments = d.get("launch_arguments", self.launch_arguments)
                self.console_minimized = d.get("console_minimized", self.console_minimized)
                theme = d.get("theme", self.theme)
                self.theme = theme if theme in THEMES else DEFAULT_THEME
                self.onboarded = bool(d.get("onboarded", self.onboarded))
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
                    "launch_arguments": self.launch_arguments,
                    "console_minimized": self.console_minimized,
                    "theme": self.theme,
                    "onboarded": self.onboarded,
                },
                f, indent=2,
            )
