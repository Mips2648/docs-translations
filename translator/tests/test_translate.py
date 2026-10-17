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


def test_get_deepl_glossary_for_language_returns_compatible_glossary(tmp_path: Path, monkeypatch) -> None:
    glossary = type("Glossary", (), {
        "name": "Documentation terms",
        "dictionaries": [type("Dictionary", (), {"target_lang": "EN"})()],
    })()
    received = {}
    client = type("DeepLClient", (), {
        "list_multilingual_glossaries": lambda self: [glossary],
        "translate_text": lambda self, *args, **kwargs: received.update(kwargs) or type(
            "Translation", (), {"text": "Hello"}
        )(),
    })()
    monkeypatch.setattr("translator.translator.deepl.DeepLClient", lambda key: client)
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
    )

    translator._deepl_translate("en_US", ["Bonjour"])

    assert received["glossary"] is glossary


def test_get_deepl_glossary_for_language_returns_none_for_incompatible_language(tmp_path: Path, monkeypatch) -> None:
    glossary = type("Glossary", (), {
        "name": "Documentation terms",
        "dictionaries": [type("Dictionary", (), {"target_lang": "DE"})()],
    })()
    received = {}
    client = type("DeepLClient", (), {
        "list_multilingual_glossaries": lambda self: [glossary],
        "translate_text": lambda self, *args, **kwargs: received.update(kwargs) or type(
            "Translation", (), {"text": "Hello"}
        )(),
    })()
    monkeypatch.setattr("translator.translator.deepl.DeepLClient", lambda key: client)
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
    )

    translator._deepl_translate("en_US", ["Bonjour"])

    assert received["glossary"] is None


def test_get_deepl_glossary_for_language_returns_none_when_no_glossary_exists(tmp_path: Path, monkeypatch) -> None:
    received = {}
    client = type("DeepLClient", (), {
        "list_multilingual_glossaries": lambda self: [],
        "translate_text": lambda self, *args, **kwargs: received.update(kwargs) or type(
            "Translation", (), {"text": "Hello"}
        )(),
    })()
    monkeypatch.setattr("translator.translator.deepl.DeepLClient", lambda key: client)
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
    )

    translator._deepl_translate("en_US", ["Bonjour"])

    assert received["glossary"] is None


def test_process_file_preserves_front_matter_keys_and_updates_lang(tmp_path: Path) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Bonjour": "Hola",
        "Ceci est un super plugin": "Este es un gran complemento",
    }

    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "es_ES"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text(
        "---\n"
        "layout : default\n"
        "title : Ceci est un super plugin\n"
        "plugin : Défauts\n"
        "lang : fr_FR\n"
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
        "layout : default\n"
        "title : Este es un gran complemento\n"
        "plugin : Défauts\n"
        "lang : es_ES\n"
        "pluginId: arlo\n"
        "---\n"
        "\n"
        "# Hola\n"
    )


def test_html_embed_lines_are_not_translated(tmp_path: Path) -> None:
    """Lines that are HTML embeds (link wrapping an image, iframe) must be copied as-is
    and must never be sent to DeepL, since they contain no bare text between the tags."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["es_ES"],
        cwd=tmp_path
    )

    def _fail_if_called(target_lang, texts):
        raise AssertionError(f"DeepL should not be called for HTML embed lines, got: {texts}")

    translator._deepl_translate = _fail_if_called

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "es_ES"
    src_root.mkdir(parents=True)

    link_with_image_line = (
        '<a href="https://example.com/something" target="_blank">'
        '<img src="https://example.com/images/button.png" '
        'alt="Donate" height="41" width="174"></a>'
    )
    embed_line = (
        '<iframe src="https://example.com/embed/widget" title="Widget" '
        'height="225" width="600" style="border: 0;"></iframe>'
    )

    src_file = src_root / "index.md"
    src_file.write_text(f"{link_with_image_line}\n{embed_line}\n", encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    assert parsed_file.get_translatable_texts() == set()

    target_file = target_root / "index.md"
    translator._write_target_file(parsed_file, "es_ES", target_file)

    assert target_file.read_text(encoding="utf-8") == f"{link_with_image_line}\n{embed_line}\n"


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
