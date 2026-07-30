from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List
from itertools import islice

import deepl
from deepl.api_data import MultilingualGlossaryInfo

from .structured_files import StructuredMarkdownFile
from .translation_memory import TranslationMemory

from .version import VERSION
from .consts import (
    DEFAULT_MEMORY_SUB_PATH,
    FR_FR,
    DEFAULT_DOCS_ROOT,
    LANGUAGES_TO_DEEPL,
    LANGUAGES_TO_DEEPL_GLOSSARY,
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
                 docs_roots: list[str] | None = None,
                 source_language: str = FR_FR,
                 memory_path: str | None = None,
                 use_glossary: bool = True,
                 debug: bool = False
                 ):
        self.__cwd = cwd.resolve()
        if docs_roots is None:
            docs_roots = [DEFAULT_DOCS_ROOT]
        self.__docs_roots: list[Path] = [self.__cwd / r for r in docs_roots]
        if memory_path is not None:
            self.__translation_memory_path = Path(memory_path)
        else:
            if len(self.__docs_roots) != 1:
                raise ValueError("memory_path is required when multiple docs_roots are configured")
            self.__translation_memory_path = self.__docs_roots[0] / DEFAULT_MEMORY_SUB_PATH

        self.__source_language = source_language
        self.__target_languages: list[str] = target_languages

        self.__logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        logging.getLogger('deepl').setLevel(logging.WARNING)
        if debug:
            self.__logger.setLevel(logging.DEBUG)

        self.__deepl_client = deepl.DeepLClient(deepl_api_key)
        self.__glossary: MultilingualGlossaryInfo | None = None
        self.__use_glossary = use_glossary

        self.__api_call_counter = 0
        self.__translated_lines_count = 0
        self.__updated_files_count = 0

        self.__translation_memory = TranslationMemory(self.__translation_memory_path, self.__target_languages)

        self.__logger.info(f"=== Translate docs module version {VERSION} initialized with deepl version {deepl.__version__} with following options ===")
        self.__logger.info(f"source directories: {[str(r.relative_to(self.__cwd)) for r in self.__docs_roots]}")
        self.__logger.info(f"source language: {self.__source_language}")
        self.__logger.info(f"target languages: {self.__target_languages}")
        self.__logger.info(f"translation memory path: ./{self.__translation_memory_path.relative_to(self.__cwd)}")
        self.__logger.info(f"debug: {debug}")

    def start(self) -> int:
        all_root_files: list[tuple[Path, list[StructuredMarkdownFile]]] = []

        for docs_root in self.__docs_roots:
            i18n_dir = docs_root / "i18n"
            imported = self.__translation_memory.migrate_from(i18n_dir)
            if imported > 0:
                self.__logger.info(f"Migrated {imported} translations from {i18n_dir} to translation memory.")
                self.__translation_memory.save()

            src_roots = sorted([p for p in docs_root.rglob("*") if p.is_dir() and p.name == self.__source_language])
            if not src_roots:
                self.__logger.warning(f"No source language directory '{self.__source_language}' found under {docs_root}; skipping.")
                continue

            for src_root in src_roots:
                src_files = self.__iter_markdown_files(src_root)
                if not src_files:
                    self.__logger.warning(f"No markdown files in {src_root}; skipping.")
                    continue

                parsed_files: list[StructuredMarkdownFile] = []
                for src_file_path in src_files:
                    parsed_file = StructuredMarkdownFile(src_file_path)
                    parsed_file.parse()
                    parsed_files.append(parsed_file)

                all_root_files.append((src_root, parsed_files))

        if not all_root_files:
            self.__logger.warning("No source files found in any configured root; nothing to do.")
            return 0

        all_source_translatable_texts: set[str] = set()
        for src_root, parsed_files in all_root_files:
            for parsed_file in parsed_files:
                all_source_translatable_texts.update(parsed_file.get_translatable_texts())

        self.__translation_memory.clean_unused_text_all_languages(all_source_translatable_texts)
        self.__translation_memory.save()

        for language in self.__target_languages:
            for src_root, parsed_files in all_root_files:
                for parsed_file in parsed_files:
                    src_file_path = parsed_file.src_file.relative_to(self.__cwd)
                    rel = parsed_file.src_file.relative_to(src_root)
                    target_file = src_root.parent / language / rel
                    target_file_path = target_file.relative_to(self.__cwd)
                    self.__logger.debug(f"Processing {src_file_path} -> {target_file_path} for language {language}")
                    self._write_target_file(parsed_file, language, target_file)

        self.__translation_memory.save()

        self.__logger.info(f"Number of files updated: {self.__updated_files_count}")
        self.__logger.info(f"Number of lines translated: {self.__translated_lines_count}")
        self.__logger.info(f"Number of API calls: {self.__api_call_counter}")
        self.__logger.info("=" * 120)
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
                self.__logger.warning(f"Missing translation for language '{language}': '{line.text}' in file ./{parsed_file.src_file.relative_to(self.__cwd)}")
                out_lines.append(f"{line.prefix}{line.text}{line.suffix}")
                continue
            out_lines.append(f"{line.prefix}{lang_memory[line.text]}{line.suffix}")

        new_content = "\n".join(out_lines) + "\n"
        old_content = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        changed = new_content != old_content

        if changed:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding="utf-8")
            self.__logger.info(f"Updated ./{target_file.relative_to(self.__cwd)}")
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
                translated = self._deepl_translate(language, batch_texts)

                for src, tgt in zip(batch_texts, translated):
                    self.__translated_lines_count += 1
                    lang_memory[src] = tgt

    def _deepl_translate(self, target_lang: str, texts: List[str]) -> List[str]:
        if not texts:
            return []

        try:
            translations = self.__deepl_client.translate_text(
                texts,
                source_lang=LANGUAGES_TO_DEEPL[self.__source_language],
                target_lang=LANGUAGES_TO_DEEPL[target_lang],
                preserve_formatting=True,
                context='home automation',
                glossary=self.__get_deepl_glossary_for_language(target_lang),
                model_type='prefer_quality_optimized'
            )
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

    def __get_deepl_glossary_for_language(self, target_lang: str) -> MultilingualGlossaryInfo | None:
        """Return the DeepL glossary if available for the given target language."""
        if not self.__use_glossary:
            return None

        if not self.__glossary:
            for deepl_glossary in self.__deepl_client.list_multilingual_glossaries():
                self.__logger.info(f"Found glossary: {deepl_glossary.name}")
                self.__glossary = deepl_glossary

        deepl_target_language = LANGUAGES_TO_DEEPL_GLOSSARY[target_lang]
        return self.__glossary if (
            self.__glossary is not None
            and deepl_target_language is not None
            and any(dictionary.target_lang == deepl_target_language for dictionary in self.__glossary.dictionaries)
        ) else None

    def __iter_markdown_files(self, root: Path) -> List[Path]:
        return sorted([p for p in root.rglob("*.md") if p.is_file()])
