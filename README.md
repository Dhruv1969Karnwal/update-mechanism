# Python Update Mechanism System

A simple, robust Python-based update mechanism consisting of two main scripts for managing application updates through GitHub releases.

## Quick Start

### For Users (Applying Updates)

```bash
# Check available versions
python update.py --repo yourname/yourapp --list

# Update to specific version
python update.py 1.2.3 --repo yourname/yourapp

# Interactive mode
python update.py --repo yourname/yourapp
```

### For Developers (Creating Releases)

```bash
# Preview changes (dry run)
python release.py --dry-run --repo yourname/yourapp

# Create release (auto-detects version)
python release.py --repo yourname/yourapp

# Create specific version
python release.py --repo yourname/yourapp --version 1.2.3
```

## Files

- **`update.py`** - User-side update script
- **`release.py`** - Developer-side release script  
- **`version.py`** - Version utility module
- **`version.json`** - Current application version
- **`manifest.json`** - Release manifest (generated)
- **`DEVELOPMENT_ARCHITECTURE.md`** - Detailed documentation

## Features

✅ **Semantic Versioning** - Automatic version bump detection  
✅ **Sequential Updates** - Handles intermediate versions automatically  
✅ **GitHub Integration** - Uses GitHub releases for distribution  
✅ **Security** - Path validation and file integrity checks  
✅ **Backup** - Automatic backup before updates  
✅ **Dependencies** - Automatic requirement installation  
✅ **Error Handling** - Comprehensive error reporting and recovery  

## Version Detection

- **Major**: Breaking changes (config, database, schema files)
- **Minor**: New features (new files, modules)
- **Patch**: Bug fixes (existing file modifications)

## Requirements

- Python 3.7+
- Git repository
- GitHub personal access token (for releases)

## Environment Setup

Set your GitHub token for releases:
```bash
export GITHUB_TOKEN=your_github_personal_access_token
```

## Example Workflow

1. **Developer**: Make changes to codebase
2. **Developer**: Run `python release.py --dry-run` to preview
3. **Developer**: Run `python release.py` to create release
4. **User**: Run `python update.py --list` to see updates
5. **User**: Run `python update.py 1.2.3` to apply update

## Documentation

See [`DEVELOPMENT_ARCHITECTURE.md`](DEVELOPMENT_ARCHITECTURE.md) for complete documentation including:
- Detailed architecture explanation
- Error handling procedures
- Security considerations
- Troubleshooting guide
- Best practices

## License

This project uses only standard Python libraries - no external dependencies required.