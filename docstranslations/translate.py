from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import deepl

from .version import VERSION
from .cache import CacheManager
from .consts import (
    ALL_LANGUAGES,
    FR_FR,
    DEFAULT_DOCS_ROOT,
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
FRONT_MATTER_LINE_RE = re.compile(r"^(\s*)([^:#][^:]*?)(\s*:\s*)(.*)$")
FRONT_MATTER_TEXT_KEYS = {"title", "description", "summary", "excerpt", "subtitle", "headline"}


@dataclass
class _RenderContext:
    lang_cache: Dict[str, str]
    target_translation_map: Dict[str, str]
    missing_hash_to_text: Dict[str, str] = field(default_factory=dict)
    rendered: List[Tuple[bool, str, str, str, str]] = field(default_factory=list)
    observed_hashes: set[str] = field(default_factory=set)


@dataclass
class _FrontMatterState:
    in_front_matter: bool = False
    front_matter_allowed: bool = True


class DocsTranslator:

    def __init__(self, cwd: Path = Path.cwd(), docs_root: str = DEFAULT_DOCS_ROOT, cache_path: Path | None = None):
        self.__cwd = cwd.resolve()
        self.__docs_root = self.__cwd / docs_root

        self.__source_language = FR_FR
        self.__target_languages: list[str] = []

        self.__logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        logging.getLogger('deepl').setLevel(logging.WARNING)

        self.__deepl_translator: deepl.Translator | None = None
        self.__deepl_api_key: str | None = None
        self.__api_call_counter = 0

        self.__cache_file = self.__docs_root / ".translation-cache" if cache_path is None else cache_path
        self.__cache_file = self.__cache_file / "deepl-cache.json"

        self.__get_inputs()

        self.__cache_manager = CacheManager(self.__cache_file)

        self.__logger.info(f"Translate docs module version {VERSION} initialized with deepl version {deepl.__version__}")

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
            observed_hashes_in_language: set[str] = set()

            for src_file in src_files:
                rel = src_file.relative_to(src_root)
                target_file = self.__docs_root / language / rel
                changed, translated_lines, file_hashes = self.process_file(
                    src_file=src_file,
                    target_file=target_file,
                    language=language
                )
                observed_hashes_in_language.update(file_hashes)
                total_translated_lines += translated_lines
                if changed:
                    updated_files += 1
                    self.__logger.info(f"Updated {target_file.relative_to(self.__docs_root)}")

            # Clean cache for this language after all files processed
            self.__cache_manager.clean_unused_hashes(language, observed_hashes_in_language)

        self.__cache_manager.save()

        self.__logger.info(f"Done. Updated files: {updated_files}, translated lines: {total_translated_lines}, api calls: {self.__api_call_counter}")
        return 0

    def __get_inputs(self):
        self.__source_language = self._get_input_in_list(INPUT_SOURCE_LANGUAGE, ALL_LANGUAGES)
        self.__target_languages = self._get_list_input(INPUT_TARGET_LANGUAGES, ALL_LANGUAGES)
        self.__deepl_api_key = self._get_input(INPUT_DEEPL_API_KEY)
        debug = self._get_boolean_input(INPUT_DEBUG)
        if debug:
            self.__logger.setLevel(logging.DEBUG)

        self.__logger.info("=== Run docs translation with following options ===")
        self.__logger.info(f"source directory: {self.__docs_root}")
        self.__logger.info(f"source language: {self.__source_language}")
        self.__logger.info(f"target languages: {self.__target_languages}")
        self.__logger.info(f"cache path: {self.__cache_file}")
        self.__logger.info(f"debug: {debug}")
        self.__logger.info(f"deepl api key present: {self.__deepl_api_key is not None}")
        self.__logger.info("=====================================================\n")

    def _get_input(self, name: str) -> str | None:
        val = os.getenv(name, '').strip()
        return val if val != '' else None

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

    def looks_translatable_front_matter_value(self, key: str, value: str) -> bool:
        normalized_key = key.strip().lower()
        if normalized_key == "lang":
            return False

        if normalized_key in FRONT_MATTER_TEXT_KEYS:
            return self.looks_translatable(value)

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return self.looks_translatable(value[1:-1])

        return self.looks_translatable(value) and any(ch.isspace() for ch in value)

    def looks_like_front_matter_start(self, lines: List[str], start_index: int) -> bool:
        if lines[start_index].strip() != "---":
            return False

        saw_key_value_line = False
        for candidate in lines[start_index + 1:]:
            stripped = candidate.strip()
            if stripped == "":
                continue
            if stripped == "---":
                return saw_key_value_line
            if FRONT_MATTER_LINE_RE.match(candidate):
                saw_key_value_line = True
                continue
            return False

        return False

    def queue_translatable_text(
        self,
        prefix: str,
        text: str,
        suffix: str,
        context: _RenderContext,
    ) -> None:
        text_hash = self.sha256_text(text)
        context.observed_hashes.add(text_hash)
        if text_hash not in context.lang_cache and text_hash in context.target_translation_map:
            # Seed cache from an existing marked translation to preserve manual edits.
            context.lang_cache[text_hash] = context.target_translation_map[text_hash]

        if text_hash not in context.lang_cache:
            context.missing_hash_to_text[text_hash] = text

        context.rendered.append((True, prefix, text, suffix, text_hash))

    def __process_front_matter_line(
        self,
        src_lines: List[str],
        idx: int,
        src_line: str,
        language: str,
        in_code_src: bool,
        front_matter_state: _FrontMatterState,
        context: _RenderContext,
    ) -> bool:
        stripped = src_line.strip()

        if front_matter_state.front_matter_allowed and not in_code_src and stripped == "---" and self.looks_like_front_matter_start(src_lines, idx):
            context.rendered.append((False, "", src_line, "", ""))
            front_matter_state.in_front_matter = True
            return True

        if front_matter_state.front_matter_allowed and not front_matter_state.in_front_matter and stripped != "":
            front_matter_state.front_matter_allowed = False

        if not front_matter_state.in_front_matter:
            return False

        if stripped == "---":
            context.rendered.append((False, "", src_line, "", ""))
            front_matter_state.in_front_matter = False
            front_matter_state.front_matter_allowed = False
            return True

        front_matter_match = FRONT_MATTER_LINE_RE.match(src_line)
        if front_matter_match:
            indent = front_matter_match.group(1)
            key = front_matter_match.group(2)
            separator = front_matter_match.group(3)
            value = front_matter_match.group(4)

            if key.strip().lower() == "lang":
                context.rendered.append((False, "", f"{indent}{key}{separator}{language}", "", ""))
                return True

            if self.looks_translatable_front_matter_value(key, value):
                prefix = f"{indent}{key}{separator}"
                suffix = ""
                text = value

                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    prefix = f"{prefix}{value[0]}"
                    suffix = value[-1]
                    text = value[1:-1]

                self.queue_translatable_text(
                    prefix=prefix,
                    text=text,
                    suffix=suffix,
                    context=context,
                )
                return True

        context.rendered.append((False, "", src_line, "", ""))
        return True

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
    ) -> Tuple[bool, int, set[str]]:

        deepl_lang = LANGUAGES_TO_DEEPL[language]
        lang_cache = self.__cache_manager.get_language_cache(language)

        src_lines = src_file.read_text(encoding="utf-8").splitlines()
        target_translation_map = self.build_translation_map_from_cache(lang_cache)
        render_cache = dict(lang_cache)

        in_code_src = False
        front_matter_state = _FrontMatterState()
        context = _RenderContext(
            lang_cache=lang_cache,
            target_translation_map=target_translation_map,
        )

        for idx, src_line in enumerate(src_lines):
            if self.__process_front_matter_line(
                src_lines=src_lines,
                idx=idx,
                src_line=src_line,
                language=language,
                in_code_src=in_code_src,
                front_matter_state=front_matter_state,
                context=context,
            ):
                continue

            src_translatable, src_prefix, src_text, src_suffix, toggle_src = self.parse_translatable_line(src_line, in_code_src)

            if toggle_src:
                in_code_src = not in_code_src

            if not src_translatable:
                context.rendered.append((False, "", src_line, "", ""))
                continue

            self.queue_translatable_text(
                prefix=src_prefix,
                text=src_text,
                suffix=src_suffix,
                context=context,
            )

        if context.missing_hash_to_text:
            hashes = list(context.missing_hash_to_text.keys())
            texts = [context.missing_hash_to_text[h] for h in hashes]

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
        for is_translatable, prefix, value, suffix, text_hash in context.rendered:
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

        return changed, translated_count, context.observed_hashes

    def iter_markdown_files(self, root: Path) -> List[Path]:
        return sorted([p for p in root.rglob("*.md") if p.is_file()])
