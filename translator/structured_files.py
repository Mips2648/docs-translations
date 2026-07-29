from typing import List
from dataclasses import field

import re
from pathlib import Path

IMAGE_ONLY_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
LINK_ONLY_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,6}\s+)(.+)$")
LIST_RE = re.compile(r"^(\s*(?:(?:[-*+]\s+|\d+\.\s+|>\s+)+))(.+)$")
FRONT_MATTER_LINE_RE = re.compile(r"^(\s*)([^:#][^:]*?)(\s*:\s*)(.*)$")
FRONT_MATTER_TEXT_KEYS = {"title", "description", "summary", "excerpt", "subtitle", "headline", "lang"}


class _Line():
    def __init__(self, translatable: bool, prefix: str, text: str, suffix: str):
        self.is_translatable = translatable
        self.prefix = prefix
        self.text = text
        self.suffix = suffix


class StructuredMarkdownFile():
    def __init__(self, src_file: Path):
        self.__src_file = src_file
        self.__parsed_source_lines: List[_Line] = []
        self.__src_lines = src_file.read_text(encoding="utf-8").splitlines()

    @property
    def src_file(self) -> Path:
        return self.__src_file

    def parse(self):
        self._in_front_matter: bool = False
        self._front_matter_allowed: bool = True
        self._in_code_src: bool = False

        for idx, src_line in enumerate(self.__src_lines):
            if self.__process_front_matter_line(
                idx=idx,
                line=src_line
            ):
                continue

            self.__parse_line(src_line)

    def get_translatable_texts(self) -> set[str]:
        return {line.text for line in self.__parsed_source_lines if line.is_translatable}

    def get_parsed_lines(self) -> list[_Line]:
        return list(self.__parsed_source_lines)

    def __add_non_translatable_line(self, line: str) -> None:
        self.__parsed_source_lines.append(_Line(False, "", line, ""))

    def __add_translatable_line(self, prefix: str, line: str, suffix: str = "") -> None:
        self.__parsed_source_lines.append(_Line(True, prefix, line, suffix))

    def __process_front_matter_line(
        self,
        idx: int,
        line: str
    ) -> bool:
        stripped = line.strip()

        if self._front_matter_allowed and stripped == "---" and self.looks_like_front_matter_start(self.__src_lines, idx):
            # Start of front matter
            self.__add_non_translatable_line(line)
            self._in_front_matter = True
            return True

        if self._front_matter_allowed and not self._in_front_matter and stripped != "":
            # If we encounter a non-empty line before front matter, we disable front matter processing for the rest of the file.
            self._front_matter_allowed = False

        if not self._in_front_matter:
            # If we are not in front matter, we don't process front matter lines.
            return False

        if stripped == "---":
            # End of front matter
            self.__add_non_translatable_line(line)
            self._in_front_matter = False
            self._front_matter_allowed = False
            return True

        front_matter_match = FRONT_MATTER_LINE_RE.match(line)
        if front_matter_match:
            indent = front_matter_match.group(1)
            key = front_matter_match.group(2)
            separator = front_matter_match.group(3)
            value = front_matter_match.group(4)

            if self.__looks_translatable_front_matter_value(key, value):
                prefix = f"{indent}{key}{separator}"
                suffix = ""
                text = value

                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    prefix = f"{prefix}{value[0]}"
                    suffix = value[-1]
                    text = value[1:-1]

                self.__add_translatable_line(prefix, text, suffix)
                return True

        self.__add_non_translatable_line(line)
        return True

    def __parse_line(self, line: str) -> None:
        stripped = line.rstrip("\n")

        if stripped.lstrip().startswith("```"):
            self._in_code_src = not self._in_code_src
            self.__add_non_translatable_line(line)
            return

        if self._in_code_src:
            self.__add_non_translatable_line(line)
            return

        if stripped.strip() == "":
            self.__add_non_translatable_line(line)
            return

        image = IMAGE_ONLY_RE.match(stripped)
        if image:
            alt_text = image.group(1)
            target = image.group(2)
            if alt_text and self.__looks_translatable(alt_text):
                self.__add_translatable_line("![", alt_text, f"]({target})")
                return
            self.__add_non_translatable_line(line)
            return

        link = LINK_ONLY_RE.match(stripped)
        if link:
            link_text = link.group(1)
            target = link.group(2)
            if link_text and self.__looks_translatable(link_text):
                self.__add_translatable_line("[", link_text, f"]({target})")
                return
            self.__add_non_translatable_line(line)
            return

        heading = HEADING_RE.match(stripped)
        if heading:
            text = heading.group(2).strip()
            if self.__looks_translatable(text):
                self.__add_translatable_line(heading.group(1), text)
                return
            self.__add_non_translatable_line(line)
            return

        list_item = LIST_RE.match(stripped)
        if list_item:
            text = list_item.group(2).strip()
            if self.__looks_translatable(text):
                self.__add_translatable_line(list_item.group(1), text)
                return
            self.__add_non_translatable_line(line)
            return

        plain = stripped.strip()
        if self.__looks_translatable(plain):
            self.__add_translatable_line("", plain)
            return

        self.__add_non_translatable_line(line)
        return

    def __looks_translatable(self, text: str) -> bool:
        # If there are no alphabetic chars, skip to avoid wasting API queries.
        return any(ch.isalpha() for ch in text)

    def __looks_translatable_front_matter_value(self, key: str, value: str) -> bool:
        normalized_key = key.strip().lower()
        if normalized_key in FRONT_MATTER_TEXT_KEYS:
            return self.__looks_translatable(value)

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return self.__looks_translatable(value[1:-1])

        return self.__looks_translatable(value) and any(ch.isspace() for ch in value)

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
