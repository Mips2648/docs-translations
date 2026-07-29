from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple
from itertools import islice

import deepl

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


@dataclass
class _RenderContext:
    translations: Dict[str, str]
    missing_texts: set[str] = field(default_factory=set)
    rendered: List[_Line] = field(default_factory=list)
    observed_texts: set[str] = field(default_factory=set)
    in_code_src: bool = False


@dataclass
class _FrontMatterState:
    in_front_matter: bool = False
    front_matter_allowed: bool = True


class _Line():
    def __init__(self, translatable: bool, prefix: str, text: str, suffix: str):
        self.is_translatable = translatable
        self.prefix = prefix
        self.text = text
        self.suffix = suffix


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

        self.__deepl_translator: deepl.Translator | None = None
        self.__deepl_api_key: str = deepl_api_key
        self.__api_call_counter = 0

        self.__translation_memory = TranslationMemory(self.__translation_memory_path, self.__target_languages)

        self.__logger.info(f"=== Translate docs module version {VERSION} initialized with deepl version {deepl.__version__} with following options ===")
        self.__logger.info(f"source directory: {self.__docs_root}")
        self.__logger.info(f"source language: {self.__source_language}")
        self.__logger.info(f"target languages: {self.__target_languages}")
        self.__logger.info(f"translation memory path: {self.__translation_memory_path}")
        self.__logger.info(f"debug: {debug}")
        self.__logger.info(f"deepl api key present: {self.__deepl_api_key is not None}")
        self.__logger.info("=====================================================\n")

    def start(self) -> int:
        src_root = self.__docs_root / self.__source_language
        if not src_root.exists():
            self.__logger.warning(f"Source language {src_root} not found; nothing to do.")
            return 0

        src_files = self.iter_markdown_files(src_root)
        if not src_files:
            self.__logger.warning(f"No markdown files in {src_root}; nothing to do.")
            return 0

        i18n_dir = self.__docs_root / "i18n"
        imported = self.__translation_memory.migrate_from(i18n_dir)
        if imported > 0:
            self.__logger.info(f"Migrated {imported} translations from {i18n_dir} to translation memory.")
            self.__translation_memory.save()

        self.__deepl_translator = deepl.Translator(self.__deepl_api_key)

        updated_files = 0
        total_translated_lines = 0

        for language in self.__target_languages:
            observed_texts_in_language: set[str] = set()

            for src_file in src_files:
                rel = src_file.relative_to(src_root)
                target_file = self.__docs_root / language / rel
                self.__logger.debug(f"Processing {src_file} -> {target_file} for language {language}")
                changed, translated_lines, file_texts = self.process_file(
                    src_file=src_file,
                    target_file=target_file,
                    language=language
                )
                observed_texts_in_language.update(file_texts)
                total_translated_lines += translated_lines
                if changed:
                    updated_files += 1
                    self.__logger.info(f"Updated {target_file.relative_to(self.__docs_root)}")

            # Clean cache for this language after all files processed
            self.__translation_memory.clean_unused_text(language, observed_texts_in_language)

        self.__translation_memory.save()

        self.__logger.info(f"Done. Updated files: {updated_files}, translated lines: {total_translated_lines}, api calls: {self.__api_call_counter}")
        return 0

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
        context.observed_texts.add(text)

        if text not in context.translations:
            context.missing_texts.add(text)

        context.rendered.append(_Line(True, prefix, text, suffix))

    def __process_front_matter_line(
        self,
        src_lines: List[str],
        idx: int,
        src_line: str,
        language: str,
        front_matter_state: _FrontMatterState,
        context: _RenderContext,
    ) -> bool:
        stripped = src_line.strip()

        if front_matter_state.front_matter_allowed and not context.in_code_src and stripped == "---" and self.looks_like_front_matter_start(src_lines, idx):
            context.rendered.append(_Line(False, "", src_line, ""))
            front_matter_state.in_front_matter = True
            return True

        if front_matter_state.front_matter_allowed and not front_matter_state.in_front_matter and stripped != "":
            front_matter_state.front_matter_allowed = False

        if not front_matter_state.in_front_matter:
            return False

        if stripped == "---":
            context.rendered.append(_Line(False, "", src_line, ""))
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
                context.rendered.append(_Line(False, "", f"{indent}{key}{separator}{language}", ""))
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

        context.rendered.append(_Line(False, "", src_line, ""))
        return True

    def parse_line(self, line: str, context: _RenderContext) -> None:
        """Return tuple: (translatable, prefix, text, suffix)."""
        stripped = line.rstrip("\n")

        if stripped.lstrip().startswith("```"):
            context.in_code_src = not context.in_code_src
            context.rendered.append(_Line(False, "", line, ""))
            return

        if context.in_code_src:
            context.rendered.append(_Line(False, "", line, ""))
            return

        if stripped.strip() == "":
            context.rendered.append(_Line(False, "", line, ""))
            return

        image = IMAGE_ONLY_RE.match(stripped)
        if image:
            alt_text = image.group(1)
            target = image.group(2)
            if alt_text and self.looks_translatable(alt_text):
                self.queue_translatable_text(
                    prefix="![",
                    text=alt_text,
                    suffix=f"]({target})",
                    context=context,
                )
                return
            context.rendered.append(_Line(False, "", line, ""))
            return

        link = LINK_ONLY_RE.match(stripped)
        if link:
            link_text = link.group(1)
            target = link.group(2)
            if link_text and self.looks_translatable(link_text):
                self.queue_translatable_text(
                    prefix="[",
                    text=link_text,
                    suffix=f"]({target})",
                    context=context,
                )
                return
            context.rendered.append(_Line(False, "", line, ""))
            return

        heading = HEADING_RE.match(stripped)
        if heading:
            text = heading.group(2).strip()
            if self.looks_translatable(text):
                self.queue_translatable_text(
                    prefix=heading.group(1),
                    text=text,
                    suffix="",
                    context=context,
                )
                return
            context.rendered.append(_Line(False, "", line, ""))
            return

        list_item = LIST_RE.match(stripped)
        if list_item:
            text = list_item.group(2).strip()
            if self.looks_translatable(text):
                self.queue_translatable_text(
                    prefix=list_item.group(1),
                    text=text,
                    suffix="",
                    context=context,
                )
                return
            context.rendered.append(_Line(False, "", line, ""))
            return

        plain = stripped.strip()
        if self.looks_translatable(plain):
            self.queue_translatable_text(
                prefix="",
                text=plain,
                suffix="",
                context=context,
            )
            return

        context.rendered.append(_Line(False, "", line, ""))
        return

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

    def process_file(
        self,
        src_file: Path,
        target_file: Path,
        language: str
    ) -> Tuple[bool, int, set[str]]:

        deepl_lang = LANGUAGES_TO_DEEPL[language]
        lang_memory = self.__translation_memory.get_language_memory(language)

        src_lines = src_file.read_text(encoding="utf-8").splitlines()

        front_matter_state = _FrontMatterState()
        context = _RenderContext(
            translations=lang_memory,
        )

        for idx, src_line in enumerate(src_lines):
            if self.__process_front_matter_line(
                src_lines=src_lines,
                idx=idx,
                src_line=src_line,
                language=language,
                front_matter_state=front_matter_state,
                context=context,
            ):
                continue

            self.parse_line(src_line, context)

        if context.missing_texts:

            batch_size = 40
            it = iter(context.missing_texts)
            while True:
                batch_texts = list(islice(it, batch_size))
                if not batch_texts:
                    break

                translated, batch_calls = self.deepl_translate(deepl_lang, batch_texts)
                self.__api_call_counter += batch_calls

                for src, tgt in zip(batch_texts, translated):
                    lang_memory[src] = tgt

        out_lines: List[str] = []
        translated_count = 0
        for line in context.rendered:
            if not line.is_translatable:
                out_lines.append(line.text)
                continue
            if line.text not in lang_memory:
                self.__logger.warning(f"Missing translation for language '{language}': '{line.text}' in file {src_file.relative_to(self.__docs_root)}")
                out_lines.append(f"{line.prefix}{line.text}{line.suffix}")
                continue
            translated_value = lang_memory[line.text]
            out_lines.append(f"{line.prefix}{translated_value}{line.suffix}")
            if translated_value != line.text:
                translated_count += 1

        new_content = "\n".join(out_lines) + "\n"
        old_content = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        changed = new_content != old_content

        if changed:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding="utf-8")

        return changed, translated_count, context.observed_texts

    def iter_markdown_files(self, root: Path) -> List[Path]:
        return sorted([p for p in root.rglob("*.md") if p.is_file()])
