# Docs Translations

A composite GitHub Action that translates Markdown documentation with DeepL and proposes changes through a pull request.

[![Tests](https://github.com/Mips2648/docs-translations/actions/workflows/pytest.yml/badge.svg)](https://github.com/Mips2648/docs-translations/actions/workflows/pytest.yml)

## How It Works

The action:

1. recursively discovers all `<source_language>` folders anywhere under each `<documents_root>`,
2. translates missing texts into each target language,
3. writes translated files next to each discovered source folder (`<parent>/<target_language>`), preserving the full directory structure,
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

Source language folders are discovered **recursively** inside each `documents_root`. This means you can have multiple versioned or grouped sub-sections, each with their own `fr_FR` folder:

```text
docs/
  fr_FR/          ← discovered and translated
  en_US/          ← generated here
  beta/
    fr_FR/        ← also discovered and translated
    en_US/        ← generated here (same relative structure)
  .translation_memory/
```

If you have a central repository for your documentation, you probably have a structure like this multi-root example:

```text
arlo/
  fr_FR/
  en_US/
  es_ES/
  beta/
    fr_FR/
    en_US/
    es_ES/
portainer/
  fr_FR/
  en_US/
  es_ES/
  beta/
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

- All `<source_language>` folders found recursively under each `<documents_root>` are processed.
- Translations are written alongside each discovered source folder: `<parent_of_source_language_folder>/<target_language>`.
- Translation memory is stored as JSON, one file per language (`<language>.json`).
- If no files change, the PR creation step does not create a PR.
- This workflow does not create a glossary due to the limitation on deepl free account on which only one glossary is allowed. So it is assumed that you also use the action `Mips2648/plugins-translations` and that the glossary has been already created by this action.

### Front Matter

Markdown front matter is processed when it starts at the beginning of a file with `---`, contains at least one `key: value` entry, and ends with another `---` before any other non-empty content.

The values of the following keys are translated when they contain alphabetic characters:

```text
title, description, summary, excerpt, subtitle, headline
```

The `lang` value is handled specially: the source language is replaced directly with the target language and is not sent to DeepL. Keys and non-translatable values are preserved. For other keys, an unquoted value is translated only when it contains whitespace, while a quoted value is translated when it contains alphabetic characters.

For example, when translating to `es_ES`:

```yaml
---
layout : default
title : Plugin pour faire le café
plugin : Défauts
lang : fr_FR
---
```

becomes conceptually:

```yaml
---
layout : default
title : <translated title>
plugin : Défauts
lang : es_ES
---
```

## PR Behavior

The action uses `peter-evans/create-pull-request` with:

- branch: `docs-translations`
- title: `[CI] Update docs translations`
- commit message: `chore(docs): update translations`

The PR includes changes from all processed roots in the run.

## Sponsor

<iframe src="https://github.com/sponsors/Mips2648/card" title="Sponsor Mips2648" height="225" width="600" style="border: 0;"></iframe>
<iframe src="https://github.com/sponsors/Mips2648/button" title="Sponsor Mips2648" height="32" width="114" style="border: 0; border-radius: 6px;"></iframe>