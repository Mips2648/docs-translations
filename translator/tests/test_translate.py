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
