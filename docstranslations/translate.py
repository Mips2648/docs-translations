from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

import deepl

from .version import VERSION
from .cache import CacheManager
from .consts import (
    ALL_LANGUAGES,
    FR_FR,
    DEFAULT_DOCS_ROOT,
    INPUT_DOCS_ROOT,
    INPUT_SOURCE_LANGUAGE,
    INPUT_DEBUG,
    INPUT_DEEPL_API_KEY,
    INPUT_TARGET_LANGUAGES,
    LANGUAGES_TO_DEEPL,
    LOG_FORMAT,
)

IMAGE_ONLY_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
LINK_ONLY_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,6}\s+)(.+)$")
LIST_RE = re.compile(r"^(\s*(?:(?:[-*+]\s+|\d+\.\s+|>\s+)+))(.+)$")


class DocsTranslator:

    def __init__(self, cwd: Path = Path.cwd()):
        self.__cwd = cwd.resolve()
        self.__docs_root = self.__cwd / DEFAULT_DOCS_ROOT

        self.__source_language = FR_FR
        self.__target_languages: list[str] = []

        self.__logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        logging.getLogger('deepl').setLevel(logging.WARNING)

        self.__deepl_translator: deepl.Translator | None = None
        self.__deepl_api_key: str | None = None
        self.__api_call_counter = 0

        self.__get_inputs()

        self.__cache_path = self.__docs_root / ".translation-cache" / "deepl-cache.json"
        self.__cache_manager = CacheManager(self.__cache_path)

        # self.__glossary: dict[str, deepl.GlossaryInfo | None] = {lang: None for lang in self.__target_languages}

        self.__logger.info(f"Translate plugin module version {VERSION} initialized with deepl version {deepl.__version__}")

    def start(self) -> int:
        if not self.__deepl_api_key:
            self.__logger.warning("DeepL API key not provided. Set the input 'deepl_api_key' to a valid key to enable translations.")
            return 0

        src_root = self.__docs_root / self.__source_language
        if not src_root.exists():
            self.__logger.warning(f"Source language {src_root} not found; nothing to do.")
            return 0

        src_files = self.iter_markdown_files(src_root)
        if not src_files:
            self.__logger.warning(f"No markdown files in {src_root}; nothing to do.")
            return 0

        self.__deepl_translator = deepl.Translator(self.__deepl_api_key)

        updated_files = 0
        total_translated_lines = 0

        for language in self.__target_languages:

            for src_file in src_files:
                rel = src_file.relative_to(src_root)
                target_file = self.__docs_root / language / rel
                changed, translated_lines = self.process_file(
                    src_file=src_file,
                    target_file=target_file,
                    language=language
                )
                total_translated_lines += translated_lines
                if changed:
                    updated_files += 1
                    self.__logger.info(f"Updated {target_file.relative_to(self.__docs_root)}")

        self.__cache_manager.save()

        self.__logger.info(f"Done. Updated files: {updated_files}, translated lines: {total_translated_lines}, api calls: {self.__api_call_counter}")
        return 0

    def __get_inputs(self):
        self.__docs_root = self._get_path_input(INPUT_DOCS_ROOT, self.__docs_root)
        self.__source_language = self._get_input_in_list(INPUT_SOURCE_LANGUAGE, ALL_LANGUAGES)
        self.__target_languages = self._get_list_input(INPUT_TARGET_LANGUAGES, ALL_LANGUAGES)
        self.__deepl_api_key = self._get_input(INPUT_DEEPL_API_KEY)
        debug = self._get_boolean_input(INPUT_DEBUG)
        if debug:
            self.__logger.setLevel(logging.DEBUG)

        self.__logger.info("=== Run plugin translation with following options ===")
        self.__logger.info(f"source directory: {self.__docs_root}")
        self.__logger.info(f"source language: {self.__source_language}")
        self.__logger.info(f"target languages: {self.__target_languages}")
        self.__logger.info(f"debug: {debug}")
        self.__logger.info(f"deepl api key present: {self.__deepl_api_key is not None}")
        self.__logger.info("=====================================================")

    def _get_input(self, name: str) -> str | None:
        val = os.getenv(name, '').strip()
        return val if val != '' else None

    def _get_path_input(self, name: str, default: Path) -> Path:
        value = self._get_input(name)
        path = Path(value) if value is not None else default
        if not path.is_absolute():
            path = self.__cwd / path
        return path.resolve()

    def _get_boolean_input(self, name: str) -> bool:
        val = self._get_input(name)
        true_values = ['true', 'True', 'TRUE']
        false_values = ['false', 'False', 'FALSE']
        if val in true_values:
            return True
        elif val in false_values:
            return False
        else:
            raise ValueError(f'Input does not meet specifications: {name}.\n Support boolean input list: "true | True | TRUE | false | False | FALSE"')

    def _get_list_input(self, name: str, allowed_values: list) -> list[str]:
        val = self._get_input(name)
        if val is None:
            raise ValueError(f'Input does not meet specifications: {name}.\n {name} is required')
        values = [s.strip() for s in val.split(',')]
        for s in values:
            if s not in allowed_values:
                raise ValueError(f'Input does not meet specifications: {name}.\n {s} not in list: {allowed_values}')
        return values

    def _get_input_in_list(self, name: str, allowed_values: list) -> str:
        val = self._get_input(name)
        if val is None or val not in allowed_values:
            raise ValueError(f'Input does not meet specifications: {name}.\n {val} not in list: {allowed_values}')
        return val

    def sha256_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def looks_translatable(self, text: str) -> bool:
        # If there are no alphabetic chars, skip to avoid wasting API queries.
        return any(ch.isalpha() for ch in text)

    def parse_translatable_line(self, line: str, in_code_block: bool) -> Tuple[bool, str, str, str, bool]:
        """Return tuple: (translatable, prefix, text, suffix, toggles_code_block)."""
        stripped = line.rstrip("\n")

        if stripped.lstrip().startswith("```"):
            return False, "", "", "", True

        if in_code_block:
            return False, "", "", "", False

        if stripped.strip() == "":
            return False, "", "", "", False

        image = IMAGE_ONLY_RE.match(stripped)
        if image:
            alt_text = image.group(1)
            target = image.group(2)
            if alt_text and self.looks_translatable(alt_text):
                return True, "![", alt_text, f"]({target})", False
            return False, "", "", "", False

        link = LINK_ONLY_RE.match(stripped)
        if link:
            link_text = link.group(1)
            target = link.group(2)
            if link_text and self.looks_translatable(link_text):
                return True, "[", link_text, f"]({target})", False
            return False, "", "", "", False

        heading = HEADING_RE.match(stripped)
        if heading:
            text = heading.group(2).strip()
            if self.looks_translatable(text):
                return True, heading.group(1), text, "", False
            return False, "", "", "", False

        list_item = LIST_RE.match(stripped)
        if list_item:
            text = list_item.group(2).strip()
            if self.looks_translatable(text):
                return True, list_item.group(1), text, "", False
            return False, "", "", "", False

        plain = stripped.strip()
        if self.looks_translatable(plain):
            return True, "", plain, "", False

        return False, "", "", "", False

    def deepl_translate(self, target_lang: str, texts: List[str]) -> Tuple[List[str], int]:
        if not texts:
            return [], 0

        if self.__deepl_translator is None:
            raise RuntimeError("DeepL translator not initialized")

        try:
            translations = self.__deepl_translator.translate_text(texts, target_lang=target_lang)
        except deepl.DeepLException as exc:
            raise RuntimeError(f"DeepL error: {exc}") from exc

        if isinstance(translations, list):
            result = [item.text for item in translations]
        else:
            result = [translations.text]
        if len(result) != len(texts):
            raise RuntimeError("DeepL response size mismatch")
        return result, 1

    def load_json(self, path: Path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def build_translation_map_from_cache(self, lang_cache: Dict[str, str]) -> Dict[str, str]:
        return dict(lang_cache)

    def process_file(
        self,
        src_file: Path,
        target_file: Path,
        language: str
    ) -> Tuple[bool, int]:

        deepl_lang = LANGUAGES_TO_DEEPL[language]
        lang_cache = self.__cache_manager.get_language_cache(language)

        src_lines = src_file.read_text(encoding="utf-8").splitlines()
        target_translation_map = self.build_translation_map_from_cache(lang_cache)
        render_cache = dict(lang_cache)

        in_code_src = False

        missing_hash_to_text: Dict[str, str] = {}
        rendered: List[Tuple[bool, str, str, str, str]] = []

        for idx, src_line in enumerate(src_lines):
            src_translatable, src_prefix, src_text, src_suffix, toggle_src = self.parse_translatable_line(src_line, in_code_src)

            if toggle_src:
                in_code_src = not in_code_src

            if not src_translatable:
                rendered.append((False, "", src_line, "", ""))
                continue

            text_hash = self.sha256_text(src_text)
            if text_hash not in lang_cache and text_hash in target_translation_map:
                # Seed cache from an existing marked translation to preserve manual edits.
                lang_cache[text_hash] = target_translation_map[text_hash]

            if text_hash not in lang_cache:
                missing_hash_to_text[text_hash] = src_text

            rendered.append((True, src_prefix, src_text, src_suffix, text_hash))

        if missing_hash_to_text:
            hashes = list(missing_hash_to_text.keys())
            texts = [missing_hash_to_text[h] for h in hashes]

            batch_size = 40
            for i in range(0, len(texts), batch_size):
                batch_hashes = hashes[i: i + batch_size]
                batch_texts = texts[i: i + batch_size]
                translated, batch_calls = self.deepl_translate(deepl_lang, batch_texts)
                self.__api_call_counter += batch_calls
                for h, t in zip(batch_hashes, translated):
                    lang_cache[h] = t

        render_cache.update(lang_cache)

        out_lines: List[str] = []
        translated_count = 0
        for is_translatable, prefix, value, suffix, text_hash in rendered:
            if not is_translatable:
                out_lines.append(value)
                continue
            translated_value = render_cache[text_hash]
            out_lines.append(f"{prefix}{translated_value}{suffix}")
            if translated_value != value:
                translated_count += 1

        new_content = "\n".join(out_lines) + "\n"
        old_content = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        changed = new_content != old_content

        if changed:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding="utf-8")

        return changed, translated_count

    def iter_markdown_files(self, root: Path) -> List[Path]:
        return sorted([p for p in root.rglob("*.md") if p.is_file()])
