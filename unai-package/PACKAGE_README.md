# Unai Package Structure

This directory contains the complete `unai` library package ready for distribution.

## Files

- **`unai/`** - Main library source code
- **`pyproject.toml`** - Modern Python packaging configuration
- **`README.md`** - User documentation and usage examples
- **`LICENSE`** - MIT license
- **`MANIFEST.in`** - Package manifest for distribution

## Installation

### Development Mode (from this directory)
```bash
pip install -e .
```

### From PyPI (when published)
```bash
pip install unai
```

## Usage in Skills

After installation, skills can simply use:

```python
import unai

response = unai.get("https://api.example.com/data")
```

The library will automatically read `request_urls.txt` from the skill's directory to enforce security policies.

## Package Structure

```
unai-package/
├── unai/
│   └── __init__.py          # Main library code
├── pyproject.toml           # Package configuration
├── README.md               # User documentation
├── LICENSE                 # MIT license
├── MANIFEST.in            # Distribution manifest
└── unai.egg-info/         # Generated package metadata
```
