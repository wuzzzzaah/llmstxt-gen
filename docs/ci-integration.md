# CI integration

The point of running codexa from CI is to make `llms.txt` self-maintaining. You should never need to remember to update it by hand.

## Pre-commit hook

Add the following to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: llmstxt-gen
        name: llmstxt-gen generate
        entry: llmstxt-gen generate
        language: system
        pass_filenames: false
        always_run: true
```

Then install the hook:

```sh
pre-commit install
```

Now `llms.txt` is regenerated on every commit. Any drift is caught locally.

## GitHub Actions

### Reusable Workflow

The recommended way to use `llmstxt-gen` in GitHub Actions is via our reusable workflow. This keeps your CI configuration clean and ensures you are always using a standard setup.

Add this to `.github/workflows/llmstxt.yml`:

```yaml
name: Update llms.txt
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  llmstxt:
    uses: wuzzzzaah/llmstxt-gen/.github/workflows/llmstxt.yml@main
    permissions:
      contents: write
```

### Manual Configuration

If you need more control, you can define the steps manually:

```yaml
name: Update llms.txt
on:
  push:
    branches: [main]

jobs:
  refresh-llms-txt:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install llmstxt-gen
        run: pip install llmstxt-gen
      - name: Generate
        run: llmstxt-gen generate
      - name: Commit
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: refresh llms.txt"
          file_pattern: "llms.txt llms-full.txt"
```

If you would rather fail the build when `llms.txt` is out of date instead of auto-committing, replace the last step with:

```yaml
      - name: Verify llms.txt is up to date
        run: |
          llmstxt-gen generate
          git diff --exit-code llms.txt llms-full.txt
```

## GitLab CI

```yaml
update-llms-txt:
  image: python:3.12
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  script:
    - pip install llmstxt-gen
    - llmstxt-gen generate
    - git config user.email "ci@example.com"
    - git config user.name "ci"
    - git add llms.txt llms-full.txt
    - git diff --cached --quiet || (git commit -m "chore: refresh llms.txt" && git push)
```

## Notes

- `llmstxt-gen generate` is deterministic: the same source tree produces the same output bytes. That makes the diff-and-commit pattern safe.
- Token-budget pruning is also deterministic, but if you tighten `max_tokens_summary` your CI will rewrite the file. Plan rollouts of that change deliberately.
