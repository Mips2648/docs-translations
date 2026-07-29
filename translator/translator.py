from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List
from itertools import islice

import deepl

from .structured_files import StructuredMarkdownFile
from .translation_memory import TranslationMemory

from .version import VERSION
from .consts import (
    DEFAULT_MEMORY_SUB_PATH,
    FR_FR,
    DEFAULT_DOCS_ROOT,
    LANGUAGES_TO_DEEPL,
    LOG_FORMAT,
)

IMAGE_ONLY_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
LINK_ONLY_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,6}\s+)(.+)$")
LIST_RE = re.compile(r"^(\s*(?:(?:[-*+]\s+|\d+\.\s+|>\s+)+))(.+)$")
FRONT_MATTER_LINE_RE = re.compile(r"^(\s*)([^:#][^:]*?)(\s*:\s*)(.*)$")
FRONT_MATTER_TEXT_KEYS = {"title", "description", "summary", "excerpt", "subtitle", "headline"}


class Translator:

    def __init__(self,
                 deepl_api_key: str,
                 target_languages: list[str],
                 cwd: Path = Path.cwd(),
                 docs_root: str = DEFAULT_DOCS_ROOT,
                 source_language: str = FR_FR,
                 memory_path: str | None = None,
                 debug: bool = False
                 ):
        self.__cwd = cwd.resolve()
        self.__docs_root = self.__cwd / docs_root
        if memory_path is not None:
            self.__translation_memory_path = Path(memory_path)
        else:
            self.__translation_memory_path = self.__docs_root / DEFAULT_MEMORY_SUB_PATH

        self.__source_language = source_language
        self.__target_languages: list[str] = target_languages

        self.__logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        logging.getLogger('deepl').setLevel(logging.WARNING)
        if debug:
            self.__logger.setLevel(logging.DEBUG)

        self.__deepl_translator = deepl.Translator(deepl_api_key)
        self.__api_call_counter = 0
        self.__translated_lines_count = 0
        self.__updated_files_count = 0

        self.__translation_memory = TranslationMemory(self.__translation_memory_path, self.__target_languages)

        self.__logger.info(f"=== Translate docs module version {VERSION} initialized with deepl version {deepl.__version__} with following options ===")
        self.__logger.info(f"source directory: {self.__docs_root}")
        self.__logger.info(f"source language: {self.__source_language}")
        self.__logger.info(f"target languages: {self.__target_languages}")
        self.__logger.info(f"translation memory path: {self.__translation_memory_path}")
        self.__logger.info(f"debug: {debug}")
        self.__logger.info("=====================================================\n")

    def start(self) -> int:
        src_root = self.__docs_root / self.__source_language
        if not src_root.exists():
            self.__logger.warning(f"Source language {src_root} not found; nothing to do.")
            return 0

        src_files = self.__iter_markdown_files(src_root)
        if not src_files:
            self.__logger.warning(f"No markdown files in {src_root}; nothing to do.")
            return 0

        i18n_dir = self.__docs_root / "i18n"
        imported = self.__translation_memory.migrate_from(i18n_dir)
        if imported > 0:
            self.__logger.info(f"Migrated {imported} translations from {i18n_dir} to translation memory.")
            self.__translation_memory.save()

        parsed_files: list[StructuredMarkdownFile] = []

        for src_file_path in src_files:
            parsed_file = StructuredMarkdownFile(src_file_path)
            parsed_file.parse()
            parsed_files.append(parsed_file)

        all_source_translatable_texts: set[str] = set()
        for parsed_file in parsed_files:
            all_source_translatable_texts.update(parsed_file.get_translatable_texts())

        self.__translation_memory.clean_unused_text_all_languages(all_source_translatable_texts)
        self.__translation_memory.save()

        for language in self.__target_languages:
            for parsed_file in parsed_files:

                src_file_path = parsed_file.src_file.relative_to(self.__cwd)
                rel = parsed_file.src_file.relative_to(src_root)
                target_file = self.__docs_root / language / rel
                target_file_path = target_file.relative_to(self.__cwd)
                self.__logger.debug(f"Processing {src_file_path} -> {target_file_path} for language {language}")
                self._write_target_file(parsed_file, language, target_file)

        self.__translation_memory.save()

        self.__logger.info(f"Done. Updated files: {self.__updated_files_count}, translated lines: {self.__translated_lines_count}, api calls: {self.__api_call_counter}")
        return 0

    def _write_target_file(self, parsed_file: StructuredMarkdownFile, language: str, target_file: Path) -> None:
        out_lines: List[str] = []

        self._ensure_translation_exists(language, parsed_file)
        lang_memory = self.__translation_memory.get_language_memory(language)

        for line in parsed_file.get_parsed_lines():
            if not line.is_translatable:
                out_lines.append(line.text)
                continue
            if line.text not in lang_memory:
                self.__logger.warning(f"Missing translation for language '{language}': '{line.text}' in file {parsed_file.src_file.relative_to(self.__docs_root)}")
                out_lines.append(f"{line.prefix}{line.text}{line.suffix}")
                continue
            out_lines.append(f"{line.prefix}{lang_memory[line.text]}{line.suffix}")

        new_content = "\n".join(out_lines) + "\n"
        old_content = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        changed = new_content != old_content

        if changed:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding="utf-8")
            self.__logger.info(f"Updated {target_file.relative_to(self.__docs_root)}")
            self.__updated_files_count += 1

        return

    def _ensure_translation_exists(self, language: str, parsed_file: StructuredMarkdownFile) -> None:
        """Ensure that all translatable texts in the parsed file have translations in the memory for the given language."""
        lang_memory = self.__translation_memory.get_language_memory(language)
        missing_texts: set[str] = set()
        for text in parsed_file.get_translatable_texts():
            if text not in lang_memory:
                if text == self.__source_language:
                    lang_memory[text] = language
                else:
                    missing_texts.add(text)
        if missing_texts:
            batch_size = 40
            it = iter(missing_texts)
            while True:
                batch_texts = list(islice(it, batch_size))
                if not batch_texts:
                    break
                deepl_lang = LANGUAGES_TO_DEEPL[language]
                translated = self._deepl_translate(deepl_lang, batch_texts)

                for src, tgt in zip(batch_texts, translated):
                    self.__translated_lines_count += 1
                    lang_memory[src] = tgt

    def _deepl_translate(self, target_lang: str, texts: List[str]) -> List[str]:
        if not texts:
            return []

        if self.__deepl_translator is None:
            raise RuntimeError("DeepL translator not initialized")

        try:
            translations = self.__deepl_translator.translate_text(texts, target_lang=target_lang)
        except deepl.DeepLException as exc:
            raise RuntimeError(f"DeepL error: {exc}") from exc

        self.__api_call_counter += 1

        if isinstance(translations, list):
            result = [item.text for item in translations]
        else:
            result = [translations.text]
        if len(result) != len(texts):
            raise RuntimeError("DeepL response size mismatch")
        return result

    def __iter_markdown_files(self, root: Path) -> List[Path]:
        return sorted([p for p in root.rglob("*.md") if p.is_file()])
