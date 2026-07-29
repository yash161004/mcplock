# Contributing to mcplock

Thank you for your interest in contributing to `mcplock`! We welcome bug fixes, documentation improvements, and feature enhancements.

---

## 🛠️ Development Setup

### Requirements
- Python **3.11** or higher
- `git`
- `Node.js` / `npx` (required for running e2e integration tests against stdio MCP servers)

### Quickstart

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yash161004/mcplock.git
   cd mcplock
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install editable package with development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

---

## 🧪 Running Tests

We use `pytest` for unit and end-to-end testing:

```bash
pytest
```

> [!NOTE]
> End-to-end tests (`tests/test_connector.py`, `tests/test_action.py`, etc.) spawn real MCP servers over stdio. Make sure `npx` is installed and accessible in your system path.

---

## 📐 Code Style & Conventions

- We adhere to modern Python 3.11+ type annotations (`list[str]`, `dict[str, Any]`, `X | None`).
- Use explicit error handling and avoid broad exceptions.
- Ensure all new features or bug fixes include corresponding unit tests under `tests/`.

---

## 🚀 Pull Request Guidelines

1. **Keep PRs focused**: Address one feature or fix per pull request.
2. **Ensure tests pass**: Run `pytest` locally before pushing your branch.
3. **Write descriptive commits**: Use concise, clear commit titles.
4. **Security safety**: Never commit secret credentials, API keys, or undisclosed vulnerability details.
