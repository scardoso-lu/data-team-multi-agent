UV_CACHE_DIR ?= .uv-cache

.PHONY: sync test harness syntax setup-check install-check

sync:
	uv --cache-dir $(UV_CACHE_DIR) sync --dev

test:
	uv --cache-dir $(UV_CACHE_DIR) run pytest tests/ -v

harness:
	uv --cache-dir $(UV_CACHE_DIR) run python -m harness.run

syntax:
	uv --cache-dir $(UV_CACHE_DIR) run python -c "import ast; from pathlib import Path; [ast.parse(path.read_text(), filename=str(path)) for root in ('agents', 'shared_skills', 'tests', 'harness') for path in Path(root).rglob('*.py')]; print('syntax ok')"

setup-check:
	bash -n setup.sh

install-check:
	bash -n install.sh
