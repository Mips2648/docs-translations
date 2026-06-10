# Docs Translations

A composite GitHub Action that translates Markdown documentation with DeepL and opens one pull request containing all generated translations.

Each documentation root contains one directory per language and its own `.translation-cache` directory. A typical layout is:

```text
arlo/
  fr_FR/
  en_US/
  .translation-cache/
portainer/
  fr_FR/
  en_US/
  .translation-cache/
```

## Usage

Grant the workflow `contents: write` and `pull-requests: write` permissions, then add the action to a workflow:

```yaml
name: Translate documentation

on:
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: Mips2648/docs-translations@main
        with:
          deepl_api_key: ${{ secrets.DEEPL_API_KEY }}
          target_languages: "en_US,es_ES,de_DE"
          documents_roots: "arlo,portainer"
```

The action translates each root in sequence, then creates at most one commit and one pull request containing changes from all roots. Pull requests are not opened when the action runs in a `pull_request` event.

## Inputs

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| `deepl_api_key` | DeepL API key used for automatic translation. | `string` | Required |
| `source_language` | Language directory containing source Markdown. | `string` | `fr_FR` |
| `target_languages` | Comma-separated target language directories. | `string` | `en_US,es_ES,de_DE` |
| `documents_roots` | Comma-separated documentation roots. Entries are trimmed and must be relative paths without `..`. | `string` | `docs` |
| `debug` | Enable debug logging. | `boolean` | `false` |

Supported languages are `fr_FR`, `en_US`, `es_ES`, `de_DE`, `it_IT`, and `pt_PT`.

## Outputs

| Name | Description |
| --- | --- |
| `has_changes` | `true` when generated Markdown or translation cache files changed in any selected root; otherwise `false`. |

The generated pull request includes `.translation-cache/*.json` and translated Markdown files for every selected root and target language. Source files and unrelated files are not added to the automated commit.

## Single-root usage

`documents_roots` defaults to `docs`, so repositories with a `docs/<language>` layout only need the API key:

```yaml
- uses: Mips2648/docs-translations@main
  id: translations
  with:
    deepl_api_key: ${{ secrets.DEEPL_API_KEY }}

- name: Report translation changes
  run: echo "Translations changed: ${{ steps.translations.outputs.has_changes }}"
```
