from .consts import (
    ALL_LANGUAGES,
    DEFAULT_DOCS_ROOT,
    INPUT_SOURCE_LANGUAGE,
    INPUT_DEBUG,
    INPUT_DEEPL_API_KEY,
    INPUT_TARGET_LANGUAGES,
)
from .inputs_parser import InputsParser
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
        inputs_parser = InputsParser()
        source_language = inputs_parser.read_one_of_str(INPUT_SOURCE_LANGUAGE, ALL_LANGUAGES)
        target_languages = inputs_parser.read_list(INPUT_TARGET_LANGUAGES, ALL_LANGUAGES)
        deepl_api_key = inputs_parser.read_str(INPUT_DEEPL_API_KEY)
        use_glossary = inputs_parser.read_bool("use_glossary")
        debug = inputs_parser.read_bool(INPUT_DEBUG)

        documents_roots_str = inputs_parser.read_str("documents_roots", DEFAULT_DOCS_ROOT)

        docs_folders = _parse_documents_roots(documents_roots_str)
        memory_path = inputs_parser.read_str("memory_path")

        if deepl_api_key is None:
            raise ValueError("DeepL API key not provided. Set the input 'deepl_api_key' to a valid key to enable translations.")

        for folder in docs_folders:
            translator = Translator(
                deepl_api_key=deepl_api_key,
                source_language=source_language,
                target_languages=target_languages,
                docs_root=folder,
                memory_path=memory_path,
                use_glossary=use_glossary,
                debug=debug,
            )
            result = translator.start()
            if result != 0:
                return result

        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
