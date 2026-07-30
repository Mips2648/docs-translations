from pathlib import Path

import pytest

from translator.consts import (
    FR_FR,
    ALL_LANGUAGES
)
from translator.structured_files import StructuredMarkdownFile
from translator.translator import Translator


def test_docs_translator_init_minimal(tmp_path: Path) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    assert translator is not None
    assert isinstance(translator, Translator)


def test_start_returns_zero_when_source_folder_missing(tmp_path: Path, caplog) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    result = translator.start()

    assert result == 0
    assert "nothing to do." in caplog.text


def test_multiple_docs_roots_require_memory_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="memory_path is required when multiple docs_roots are configured"):
        Translator(
            deepl_api_key="dummy-key",
            target_languages=ALL_LANGUAGES,
            cwd=tmp_path,
            docs_roots=["docs", "plugins/docs"],
        )


def test_process_file_preserves_front_matter_keys_and_updates_lang(tmp_path: Path) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Bonjour": "Hola",
        "Documentation Arlo": "Documentación Arlo"
    }

    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "es_ES"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text(
        "---\n"
        "layout: default\n"
        "title: Documentation Arlo\n"
        "lang: fr_FR\n"
        "pluginId: arlo\n"
        "---\n"
        "\n"
        "# Bonjour\n",
        encoding="utf-8",
    )

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "es_ES", target_file)

    assert target_file.read_text(encoding="utf-8") == (
        "---\n"
        "layout: default\n"
        "title: Documentación Arlo\n"
        "lang: es_ES\n"
        "pluginId: arlo\n"
        "---\n"
        "\n"
        "# Hola\n"
    )


def test_start_translates_nested_source_language_directories(tmp_path: Path) -> None:
    """Files in nested fr_FR directories (e.g. plugin1/fr_FR and plugin1/beta/fr_FR)
    are both discovered and translated, with the target placed in the same structure."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
        docs_roots=["docs"],
        memory_path=str(tmp_path / "memory.json"),
    )

    mapping = {"Bonjour": "Hello", "Beta": "Beta"}
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    # plugin1/fr_FR/index.md
    src1 = tmp_path / "docs" / "plugin1" / FR_FR
    src1.mkdir(parents=True)
    (src1 / "index.md").write_text("# Bonjour\n", encoding="utf-8")

    # plugin1/beta/fr_FR/index.md
    src2 = tmp_path / "docs" / "plugin1" / "beta" / FR_FR
    src2.mkdir(parents=True)
    (src2 / "index.md").write_text("# Beta\n", encoding="utf-8")

    result = translator.start()

    assert result == 0

    target1 = tmp_path / "docs" / "plugin1" / "en_US" / "index.md"
    assert target1.exists(), "Expected translated file at plugin1/en_US/index.md"
    assert target1.read_text(encoding="utf-8") == "# Hello\n"

    target2 = tmp_path / "docs" / "plugin1" / "beta" / "en_US" / "index.md"
    assert target2.exists(), "Expected translated file at plugin1/beta/en_US/index.md"
    assert target2.read_text(encoding="utf-8") == "# Beta\n"
