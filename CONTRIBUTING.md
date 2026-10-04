# Contributing

Create a virtual environment and install `pip install -e '.[dev,tokens,mcp]'`.
Run `ruff check src tests benchmarks examples`, `ruff format --check src tests
benchmarks examples`, `mypy`, `python -m pytest`, and `python -m build`.

Keep the runtime core dependency-free. Use `Repository`, `Ranker` and `Counter`
ports for alternative backends and policies. New public operations need concise
contract docstrings and tests for failure, scope and lifetime behavior.

Do not weaken whole-pack accounting or accept archived-but-unexposed quotes.
Benchmarks must keep grading labels out of retrieval and model inputs. Include
all failures in the denominator, and separate synthetic stress, live fault
repair and model answer quality. Update the report and source fingerprint when
changing implementation code; do not reuse old measurements as current results.
