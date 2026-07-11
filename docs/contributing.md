# Contributing

We welcome contributions! Here's how to get started:

## Setup

```bash
git clone https://github.com/yourorg/helios.git
cd helios
pip install -e ".[dev]"
npm install --prefix web
```

## Running Tests

```bash
pytest tests/ -v
```

## Building the Frontend

```bash
cd web && npm install && npm run build
python copy_web.py --skip-build
```

## Code Style

- Use [ruff](https://github.com/astral-sh/ruff) for linting
- Type hints required on all function signatures
- Keep lines under 120 characters
- Write tests for new features

## Pull Request Process

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-thing`)
3. Make your changes with tests
4. Run `pytest` and `ruff check` to verify
5. Open a PR with a clear description

## Reporting Issues

Use the GitHub issue tracker. Include:
- Helios version
- Python version
- OS version
- Steps to reproduce
- Expected vs actual behavior