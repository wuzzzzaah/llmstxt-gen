# llmstxt-gen documentation

codexa is a command-line tool and Python library that turns the source code of a Python or JavaScript/TypeScript project into a spec-compliant [`llms.txt`](https://llmstxt.org/) pair.

It reads code, not rendered docs. That makes the output accurate by construction: if a function exists in your repository, it shows up in `llms.txt`; if you delete it, it disappears on the next run.

## Where to start

- New here? Read [quickstart.md](quickstart.md).
- Want to tune the output? See [configuration.md](configuration.md).
- Running it in CI? See [ci-integration.md](ci-integration.md).
- Curious what the output looks like? See [output-format.md](output-format.md).
- Curious how it works inside? See [architecture.md](architecture.md).

## Why AST and not scraping

A scraper sees a project the way Google does: through whatever the docs site happens to render today. The source code is the only place every public function is guaranteed to exist with its real signature. llmstxt-gen builds the answer from that ground truth.
