import pytest

from translator.__main__ import _parse_documents_roots


def test_parse_documents_roots_trims_and_deduplicates() -> None:
    assert _parse_documents_roots(" arlo, portainer ,arlo ") == ["arlo", "portainer"]


@pytest.mark.parametrize("value", ["", "arlo,", ",arlo", "arlo, ,portainer"])
def test_parse_documents_roots_rejects_empty_entries(value: str) -> None:
    with pytest.raises(ValueError, match="empty entries"):
        _parse_documents_roots(value)


@pytest.mark.parametrize("value", ["/docs", "C:\\docs", "C:/docs"])
def test_parse_documents_roots_rejects_absolute_paths(value: str) -> None:
    with pytest.raises(ValueError, match="relative paths"):
        _parse_documents_roots(value)


@pytest.mark.parametrize("value", ["../docs", "docs/../other", "docs\\..\\other", "docs..backup"])
def test_parse_documents_roots_rejects_parent_traversal(value: str) -> None:
    with pytest.raises(ValueError, match="must not contain"):
        _parse_documents_roots(value)
