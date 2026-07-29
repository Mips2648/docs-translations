from __future__ import annotations

import json
import logging
from pathlib import Path


class TranslationMemory:
    """Manage translation memory in i18n files."""

    def __init__(self, dir: Path, languages: list[str]):
        self.__logger = logging.getLogger(__name__)

        self.__translation_dir = dir
        self.__languages: list[str] = languages
        self.__data: dict[str, dict[str, str]] = {lang: self._load(lang) for lang in languages}

    def _load(self, language: str) -> dict[str, str]:
        """Load memory for a specific language from file or return default structure."""
        file = self.__translation_dir / f"{language}.json"
        try:
            content = file.read_text(encoding="utf-8")
            return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        """Save memory to file."""
        for language, data in self.__data.items():
            file = self.__translation_dir / f"{language}.json"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=4), encoding="UTF-8")

    def get_language_memory(self, language: str) -> dict[str, str]:
        """Get dictionary for a specific language."""
        data = self.__data.setdefault(language, {})
        return data

    def add_translation(self, language: str, text: str, translation: str) -> None:
        """Add a translation to the memory."""
        text = text.strip()
        translation = translation.strip()
        if not text or not translation or text == translation:
            self.__logger.debug(f"Skipping adding translation memory entry for language '{language}': text or translation is empty or identical.")
            return

        data = self.get_language_memory(language)
        data[text] = translation

    def clean_unused_text(self, language: str, active_texts: set[str]) -> int:
        """Remove memory entries for texts that no longer exist in source files.

        Returns the number of removed entries.
        """
        data = self.get_language_memory(language)
        texts_to_remove = set(data) - active_texts

        for t in texts_to_remove:
            self.__logger.debug(f"Removing unused translation memory entry for language '{language}': '{t}'")
            del data[t]

        return len(texts_to_remove)

    def clean_unused_text_all_languages(self, active_texts: set[str]) -> int:
        """Remove unused entries for all configured target languages.

        Returns the total number of removed entries across all languages.
        """
        removed_total = 0
        for language in self.__languages:
            removed_total += self.clean_unused_text(language, active_texts)
        return removed_total

    def migrate_from(self, old_dir: Path) -> int:
        """
        Migrate old i18n files from old_dir into the current memory structure.

        Returns the total number of imported translations.
        """
        imported_count = 0

        if not old_dir.exists() or not old_dir.is_dir():
            return imported_count

        for language in self.__languages:
            old_file = old_dir / f"{language}.json"

            try:
                content = old_file.read_text(encoding="utf-8")
                data = json.loads(content)
            except (FileNotFoundError, json.JSONDecodeError):
                self.__logger.debug(f"No valid old translation memory file found for language '{language}' at '{old_file}'")
                continue

            if not all(isinstance(v, dict) for v in data.values()):
                self.__logger.debug(f"Invalid structure in old translation memory file for language '{language}' at '{old_file}'")
                continue

            for entries in data.values():
                for text, translation in entries.items():
                    self.add_translation(language, text, translation)
                    imported_count += 1

            old_file.unlink()  # Remove the old file after migration

        return imported_count
