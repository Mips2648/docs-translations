import os
from pathlib import Path

from .consts import DEFAULT_DOCS_ROOT
from .translator import Translator


def _parse_documents_roots(value: str) -> list[str]:
    """Parse and validate comma-separated documentation roots."""
    roots: list[str] = []
    for entry in value.split(","):
        root = entry.strip().replace("\\", "/")
        if not root:
            raise ValueError("documents_roots must not contain empty entries")
        if "\n" in root or "\r" in root:
            raise ValueError("documents_roots entries must be single-line paths")
        # Reject absolute paths (starting with / or containing :)
        if root.startswith("/") or ":" in root:
            raise ValueError(f"documents_roots entries must be relative paths: {entry.strip()}")
        if ".." in root:
            raise ValueError(f"documents_roots entries must not contain '..'.: {entry.strip()}")
        if root not in roots:
            roots.append(root)
    return roots


def main() -> int:
    try:
        documents_roots_str = os.getenv("documents_roots", DEFAULT_DOCS_ROOT)

        roots = _parse_documents_roots(documents_roots_str)

        memory_path_str = os.getenv("memory_path")
        memory_path = Path(memory_path_str) if memory_path_str else None

        for root in roots:
            translator = Translator(docs_root=root, memory_path=memory_path)
            result = translator.start()
            if result != 0:
                return result

        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
