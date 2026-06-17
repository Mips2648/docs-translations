from pathlib import Path

from translator.consts import (
    FR_FR,
    INPUT_DEBUG,
    INPUT_SOURCE_LANGUAGE,
    INPUT_TARGET_LANGUAGES,
)
from translator.translator import Translator


def test_docs_translator_init_minimal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(INPUT_SOURCE_LANGUAGE, FR_FR)
    monkeypatch.setenv(INPUT_TARGET_LANGUAGES, "en_US")
    monkeypatch.setenv(INPUT_DEBUG, "false")

    translator = Translator(tmp_path)

    assert translator is not None
    assert isinstance(translator, Translator)


def test_start_returns_zero_when_source_folder_missing(tmp_path: Path, monkeypatch, caplog) -> None:
    monkeypatch.setenv(INPUT_SOURCE_LANGUAGE, FR_FR)
    monkeypatch.setenv(INPUT_TARGET_LANGUAGES, "en_US")
    monkeypatch.setenv(INPUT_DEBUG, "false")
    monkeypatch.setenv("documents_root", "docs")
    monkeypatch.setenv("deepl_api_key", "dummy-key")

    translator = Translator(tmp_path)

    result = translator.start()

    assert result == 0
    assert "not found; nothing to do." in caplog.text


def test_process_file_preserves_front_matter_keys_and_updates_lang(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(INPUT_SOURCE_LANGUAGE, FR_FR)
    monkeypatch.setenv(INPUT_TARGET_LANGUAGES, "es_ES")
    monkeypatch.setenv(INPUT_DEBUG, "false")

    translator = Translator(tmp_path)
    mapping = {
        "Bonjour": "Hola",
        "Documentation Arlo": "Documentación Arlo",
    }

    translator.deepl_translate = lambda target_lang, texts: (
        [mapping[t] for t in texts],
        len(texts)
    )

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

    changed, translated_count, observed_hashes = translator.process_file(src_file, target_file, "es_ES")

    assert changed is True
    assert translated_count == 2
    assert len(observed_hashes) == 2
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
