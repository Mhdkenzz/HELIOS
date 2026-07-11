.PHONY: dev install test lint clean

dev:
	@echo "Starting backend (uvicorn) + frontend (vite)…"
	@echo "Backend → http://localhost:6767"
	@echo "Frontend → http://localhost:5173"
	bash -c "cd web && npm run dev &" & \
	uvicorn helios.cli:app --reload --host 0.0.0.0 --port 6767 --log-level info

install:
	pip install -e ".[dev]"
	cd web && npm install

test:
	pytest tests/ -v --tb=short

lint:
	python -m py_compile helios/*.py
	python -m flake8 helios/ tests/ || true

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache web/node_modules web/dist *.egg-info
	rm -rf helios.egg-info/