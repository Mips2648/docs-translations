# Docs Translations

A composite GitHub Action that translates Markdown documentation with DeepL and proposes changes through a pull request.

[![Tests](https://github.com/Mips2648/docs-translations/actions/workflows/pytest.yml/badge.svg)](https://github.com/Mips2648/docs-translations/actions/workflows/pytest.yml)

## How It Works

The action:

1. reads Markdown files from the source folder (`<documents_root>/<source_language>`),
2. translates missing texts into each target language,
3. updates target files (`<documents_root>/<target_language>`),
4. updates JSON translation memory,
5. creates or updates a technical PR (`docs-translations`) when changes are detected.

A single run can process multiple documentation roots (`documents_roots`) and generate one PR for all changes.

## Expected Structure

By default, the documentation root is `docs` for a single-root use case (typical use case of a single plugin):

```text
docs/
  fr_FR/
  en_US/
  es_ES/
  de_DE/
  .translation_memory/
```

If you have a central repository for your documentation, you probably have a structure like this multi-root example:

```text
arlo/
  fr_FR/
  en_US/
  es_ES/
portainer/
  fr_FR/
  en_US/
  es_ES/
.translation_memory/
```

In this case, the translation memory will be shared between all your documents

## Prerequisites

- A valid `DEEPL_API_KEY` secret.
- The following GitHub Actions workflow permissions:
  - `contents: write`
  - `pull-requests: write`

## Usage

### Multi-root Example

```yaml
name: Translate documentation

on:
  workflow_dispatch:
    inputs:
      target_languages:
        description: "Comma-separated target languages"
        required: false
        default: "en_US,es_ES"
  push:
    branches:
      - main
    paths:
      - '**/fr_FR/*.md'

permissions:
  contents: write
  pull-requests: write

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: Mips2648/docs-translations@v3
        with:
          deepl_api_key: ${{ secrets.DEEPL_API_KEY }}
          target_languages: "en_US,es_ES,de_DE"
          documents_roots: "arlo,portainer"
          memory_path: ${{ github.workspace }}/.translation_memory
```

### Single-root Example (Default)

If your documentation is in `docs/<language>`, you only need to provide the DeepL key:

```yaml
name: Docs translate

on:
  workflow_dispatch:
    inputs:
      target_languages:
        description: "Comma-separated target languages"
        required: false
        default: "de_DE,es_ES,en_US"
  push:
    branches:
      - beta
    paths:
      - docs/fr_FR/*.md
  pull_request:
    branches:
      - beta
    paths:
      - docs/fr_FR/*.md

permissions:
  contents: write
  pull-requests: write

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: Mips2648/docs-translations@v3
        with:
            deepl_api_key: ${{ secrets.DEEPL_API_KEY }}
            target_languages: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.target_languages || 'en_US,es_ES,de_DE' }}
```

## Inputs

| Name               | Description                                                                                                                | Type      | Default             |
|--------------------|----------------------------------------------------------------------------------------------------------------------------|-----------|---------------------|
| `deepl_api_key`    | DeepL API key (required).                                                                                                  | `string`  | Required            |
| `source_language`  | Source language folder. Supported values: `fr_FR`, `en_US`, `es_ES`, `de_DE`, `it_IT`, `pt_PT`.                            | `string`  | `fr_FR`             |
| `target_languages` | Comma-separated list of target languages. Supported values: `fr_FR`, `en_US`, `es_ES`, `de_DE`, `it_IT`, `pt_PT`.          | `string`  | `en_US,es_ES,de_DE` |
| `documents_roots`  | Comma-separated documentation roots. Entries are normalized and deduplicated, must be relative, and must not contain `..`. | `string`  | `docs`              |
| `memory_path`      | Path to the translation memory directory. If empty or not provided: `<documents_root>/.translation_memory`.                | `string`  | `""`                |
| `use_glossary`     | Whether to use an existing DeepL glossary from your account. (`true`, `True`, `TRUE`, `false`, `False`, `FALSE`)           | `boolean` | `true`              |
| `debug`            | Enables verbose logs. Accepted values: `true`, `True`, `TRUE`, `false`, `False`, `FALSE`.                                  | `boolean` | `false`             |

## Important Notes

- Source files are read from `<documents_root>/<source_language>`.
- Translations are written to `<documents_root>/<target_language>`.
- Translation memory is stored as JSON, one file per language (`<language>.json`).
- If no files change, the PR creation step does not create a PR.
- This workflow does not create a glossary due to the limitation on deepl free account on which only one glossary is allowed. So it is assumed that you also use the action `Mips2648/plugins-translations` and that the glossary has been already created by this action.

## PR Behavior

The action uses `peter-evans/create-pull-request` with:

- branch: `docs-translations`
- title: `[CI] Update docs translations`
- commit message: `chore(docs): update translations`

The PR includes changes from all processed roots in the run.
