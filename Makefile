.PHONY: dev install test lint clean copy-web

# Build the web frontend and copy into the Python package
copy-web:
	cd web && npm install && npm run build && cd .. && python copy_web.py
	@echo "✓ Web assets copied into helios/"

# Start backend (with auto-reload) + frontend dev server
dev:
	@bash -c "cd web && npm run dev &" & \
	uvicorn helios.backend:create_app --reload --host 0.0.0.0 --port 6767

# Install all Python + Node dependencies
install:
	pip install -e ".[dev]"
	cd web && npm install && cd ..
	@echo "✓ Dependencies installed"

# Run all tests
test:
	pytest tests/ -v --tb=short

# Lint Python source
lint:
	python -m py_compile helios/*.py

# Clean build artifacts, caches, and node_modules
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache web/node_modules web/dist web/.nuxt
	rm -rf *.egg-info helios.egg-info
	rm -rf .venv
	@echo "✓ Clean"