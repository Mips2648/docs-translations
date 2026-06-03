from __future__ import annotations

import json
from pathlib import Path


class CacheManager:
    """Manage translation cache stored in a JSON file."""

    def __init__(self, cache_path: Path):
        self.__cache_path = cache_path
        self.__cache: dict = self._load()

    def _load(self) -> dict:
        """Load cache from file or return default structure."""
        if not self.__cache_path.exists():
            return {"languages": {}}
        try:
            with self.__cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"languages": {}}

    def save(self) -> None:
        """Save cache to file."""
        self.__cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.__cache_path.open("w", encoding="utf-8") as f:
            json.dump(self.__cache, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def get_language_cache(self, language: str) -> dict[str, str]:
        """Get cache dictionary for a specific language."""
        languages = self.__cache.setdefault("languages", {})
        return languages.setdefault(language, {})

    def add_translation(self, language: str, text_hash: str, translation: str) -> None:
        """Add a translation to the cache."""
        lang_cache = self.get_language_cache(language)
        lang_cache[text_hash] = translation

    def clean_unused_hashes(self, language: str, active_hashes: set[str]) -> int:
        """Remove cache entries for hashes that no longer exist in source files.

        Returns the number of removed entries.
        """
        lang_cache = self.get_language_cache(language)
        hashes_to_remove = [h for h in lang_cache.keys() if h not in active_hashes]

        for h in hashes_to_remove:
            del lang_cache[h]

        return len(hashes_to_remove)
