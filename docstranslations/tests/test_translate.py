from pathlib import Path

from docstranslations.consts import (
    FR_FR,
    INPUT_DEBUG,
    INPUT_SOURCE_LANGUAGE,
    INPUT_TARGET_LANGUAGES,
)
from docstranslations.translate import DocsTranslator


def test_docs_translator_init_minimal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(INPUT_SOURCE_LANGUAGE, FR_FR)
    monkeypatch.setenv(INPUT_TARGET_LANGUAGES, "en_US")
    monkeypatch.setenv(INPUT_DEBUG, "false")

    translator = DocsTranslator(tmp_path)

    assert translator is not None
    assert isinstance(translator, DocsTranslator)


def test_start_returns_zero_when_source_folder_missing(tmp_path: Path, monkeypatch, caplog) -> None:
    monkeypatch.setenv(INPUT_SOURCE_LANGUAGE, FR_FR)
    monkeypatch.setenv(INPUT_TARGET_LANGUAGES, "en_US")
    monkeypatch.setenv(INPUT_DEBUG, "false")
    monkeypatch.setenv("documents_root", "docs")
    monkeypatch.setenv("deepl_api_key", "dummy-key")

    translator = DocsTranslator(tmp_path)

    result = translator.start()

    assert result == 0
    assert "not found; nothing to do." in caplog.text
