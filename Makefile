.PHONY: install test lint demo bench clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

demo:
	blender-loop demo --out out/demo

bench:
	blender-loop bench --out out/bench

clean:
	rm -rf out build dist .pytest_cache .ruff_cache **/__pycache__
