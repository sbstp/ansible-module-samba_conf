setup-dev:
	uv sync

test:
	.venv/bin/python -m unittest
