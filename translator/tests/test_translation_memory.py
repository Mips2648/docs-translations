from pathlib import Path

from translator.consts import (
    EN_US,
    FR_FR,
    ALL_LANGUAGES
)
from translator.translation_memory import TranslationMemory


def test_translation_memory_init_minimal(tmp_path: Path) -> None:
    memory = TranslationMemory(tmp_path, ALL_LANGUAGES)

    assert memory is not None
    assert isinstance(memory, TranslationMemory)


def test_translation_memory_add_translation_and_get_language_memory(tmp_path: Path) -> None:
    memory = TranslationMemory(tmp_path, ALL_LANGUAGES)

    memory.add_translation(EN_US, "Bonjour", "Hello")
    memory.add_translation(EN_US, "Bonjour", "Hello")  # Duplicate, should be ignored
    memory.add_translation(EN_US, "Au revoir", "Goodbye")

    en_memory = memory.get_language_memory("en_US")
    assert en_memory == {"Au revoir": "Goodbye", "Bonjour": "Hello"}

    memory.save()

    # Reload and check if the data persists
    new_memory = TranslationMemory(tmp_path, ALL_LANGUAGES)
    new_en_memory = new_memory.get_language_memory("en_US")
    assert new_en_memory == {"Au revoir": "Goodbye", "Bonjour": "Hello"}


def test_translation_memory_clean_unused_text(tmp_path: Path) -> None:
    memory = TranslationMemory(tmp_path, ALL_LANGUAGES)

    memory.add_translation(EN_US, "Bonjour", "Hello")
    memory.add_translation(EN_US, "Au revoir", "Goodbye")
    memory.save()

    # Clean unused text
    active_texts = {"Bonjour"}  # Only "Bonjour" is active
    removed_count = memory.clean_unused_text(EN_US, active_texts)
    assert removed_count == 1

    en_memory = memory.get_language_memory("en_US")
    assert en_memory == {"Bonjour": "Hello"}


def test_translation_memory_migrate_from(tmp_path: Path) -> None:
    old_dir = tmp_path / "i18n"
    old_dir.mkdir()
    old_file = old_dir / "en_US.json"
    old_file.write_text(
        """
        {
            "changelog.md": {
                "IMPORTANT": "Important",
                " IMPORTANT ": " Important ",
                " IMPORTANT": " Important",
                "IMPORTANT ": "Important "
            }
        }
        """,
        encoding="utf-8"
    )

    memory = TranslationMemory(tmp_path, [EN_US])
    imported_count = memory.migrate_from(old_dir)

    en_memory = memory.get_language_memory(EN_US)
    assert en_memory == {
        "IMPORTANT": "Important"
    }

    assert imported_count == 4
    assert len(en_memory) == 1

    assert not (old_dir / "en_US.json").exists()
