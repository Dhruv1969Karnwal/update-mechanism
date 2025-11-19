# Python Update Mechanism System - Development Architecture

## Overview

This document describes the architecture and usage of the Python-based update mechanism system. The system provides a complete solution for managing application updates with version control, automatic change detection, and seamless deployment through GitHub releases.

## System Components

### Core Files

- **`update.py`** - User-side script for applying updates
- **`release.py`** - Developer-side script for creating releases
- **`version.py`** - Version utility module for parsing and comparing semantic versions
- **`version.json`** - Current version information stored in application root
- **`manifest.json`** - Release manifest describing file changes
- **`requirements.txt`** - Python dependencies (no external dependencies required)

### Architecture Flow

```
Developer Makes Changes → release.py → GitHub Release → update.py → User Update
```

## Version Management

### Semantic Versioning

The system uses semantic versioning in the format `major.minor.patch`:

- **Major**: Breaking changes (config, database, schema changes)
- **Minor**: New features (new files, modules)
- **Patch**: Bug fixes (modifications to existing files)

### Version Detection

- Current version is stored in `version.json` in the application root
- Version comparison logic ensures proper sequential updates
- Intermediate versions are automatically handled

## Release Process (`release.py`)

### Usage

```bash
# Basic usage (auto-detects version bump)
python release.py --repo owner/repository

# Specify target version
python release.py --repo owner/repository --version 1.2.3

# Dry run to preview changes
python release.py --repo owner/repository --dry-run
```

### Environment Setup

1. **Git Repository**: Must be in a git repository
2. **GitHub Token**: Set `GITHUB_TOKEN` environment variable for authentication
   ```bash
   export GITHUB_TOKEN=your_github_personal_access_token
   ```

### Release Detection Logic

The system automatically determines version bump type based on file changes:

#### Major Updates
- Changes to: `config`, `database`, `schema`, `migrate`
- Configuration files: `requirements.txt`, `setup.py`, `pyproject.toml`

#### Minor Updates
- New files with naming patterns: `module`, `feature`, `component`, `service`
- Any new files (default behavior)

#### Patch Updates
- Modifications to existing files
- File deletions

### Release Creation Process

1. **Change Analysis**: Analyzes git changes since last release
2. **Version Determination**: Calculates appropriate version bump
3. **Manifest Generation**: Creates `manifest.json` with file lists
4. **GitHub Release**: Creates release with assets
5. **Git Operations**: Commits changes and pushes to repository

### Manifest Structure

```json
{
  "version": "1.2.3",
  "files_add": ["new_file.py", "config/"],
  "files_edit": ["existing_file.py"],
  "files_delete": ["old_file.py"],
  "req.txt": true,
  "build_date": "2025-11-19"
}
```

## Update Process (`update.py`)

### Usage

```bash
# Update to specific version
python update.py 1.2.3 --repo owner/repository

# List available versions
python update.py --repo owner/repository --list

# Interactive mode (prompts for version)
python update.py --repo owner/repository
```

### Update Flow

1. **Version Detection**: Reads current version from `version.json`
2. **Validation**: Validates target version and gets user confirmation
3. **Sequential Updates**: Handles intermediate versions if needed
4. **Manifest Fetching**: Downloads release manifests from GitHub
5. **File Operations**: Applies changes (add/edit/delete files)
6. **Dependency Installation**: Updates requirements if specified
7. **Version Update**: Updates local `version.json`

### User Confirmation Logic

- **Major Updates**: Proceed automatically (breaking changes expected)
- **Minor/Patch Updates**: Requires user confirmation

### Security Features

- Filename validation to prevent path traversal attacks
- Backup creation before applying updates
- File integrity verification
- Timeout protection for network operations

## GitHub Integration

### Release Structure

Each GitHub release contains:
- `manifest.json` - Update instructions
- All files listed in manifest
- `requirements.txt` (if dependencies changed)

### API Usage

- **Releases API**: Creates and manages releases
- **Downloads**: Uses GitHub release download URLs
- **Authentication**: Supports personal access tokens

## Error Handling

### Common Scenarios

1. **Network Issues**: Timeout and retry logic
2. **Permission Errors**: File access validation
3. **Version Conflicts**: Semantic validation
4. **Git Issues**: Repository state verification
5. **API Limits**: Rate limiting handling

### Recovery Mechanisms

- Backup creation before updates
- Rollback capability
- Partial failure handling
- Detailed error reporting

## Security Considerations

### File Path Validation

- Prevents path traversal attacks (`../`, absolute paths)
- Filename sanitization
- Suspicious pattern detection

### Authentication

- GitHub token authentication recommended for releases
- Token should have `repo` scope permissions
- Environment variable storage (not hardcoded)

### Integrity Checks

- File size verification after download
- JSON structure validation
- Version format validation

## Development Workflow

### Making Changes

1. Make code changes in your development environment
2. Test changes locally
3. Run `release.py` to create new release:
   ```bash
   python release.py --repo yourname/yourapp
   ```

### Testing Updates

1. Use test repository for initial testing
2. Verify manifest generation
3. Test update process on clean environment
4. Validate version progression

### Production Deployment

1. Tag releases appropriately
2. Maintain changelog in release notes
3. Monitor update success rates
4. Keep GitHub token secure

## Configuration Options

### Customization Points

- **Target Branch**: Change from `main` in `release.py`
- **File Patterns**: Modify detection logic in `determine_version_bump()`
- **Timeout Values**: Adjust network timeouts
- **Backup Strategy**: Customize backup location

### Environment Variables

- `GITHUB_TOKEN`: Personal access token for releases
- Optional but recommended for automated workflows

## Troubleshooting

### Common Issues

1. **Git Not Initialized**: Ensure project is a git repository
2. **No Changes Detected**: Verify you have committed changes
3. **Permission Denied**: Check file permissions and GitHub token
4. **Version Conflicts**: Verify version format and uniqueness
5. **Network Timeouts**: Check internet connectivity

### Debug Mode

Add debug prints to identify issues:

```python
# In release.py
print(f"Debug: Added files: {added_files}")
print(f"Debug: Version bump: {bump_type}")

# In update.py
print(f"Debug: Current version: {current_ver}")
print(f"Debug: Target version: {target_ver}")
```

## Best Practices

### Development

1. **Commit First**: Ensure all changes are committed before releasing
2. **Version Consistency**: Maintain semantic versioning
3. **Test Releases**: Use dry-run mode to preview changes
4. **Clean History**: Maintain meaningful commit messages

### Deployment

1. **Staging Testing**: Test in staging environment first
2. **Rollback Planning**: Keep previous releases available
3. **Monitoring**: Track update success/failure rates
4. **Documentation**: Update changelog for each release

### Security

1. **Token Management**: Rotate GitHub tokens regularly
2. **Access Control**: Limit repository write access
3. **Audit Trail**: Monitor release creation logs
4. **Validation**: Verify file integrity after updates

## Example Workflow

### Initial Setup

```bash
# Initialize repository
git init
git add .
git commit -m "Initial commit"

# Create first release
python release.py --repo yourname/yourapp --version 1.0.0
```

### Feature Update

```bash
# Make changes to codebase
git add .
git commit -m "Add new feature module"

# Create release (auto-detects minor version bump)
python release.py --repo yourname/yourapp
```

### User Update

```bash
# Check available versions
python update.py --repo yourname/yourapp --list

# Update to latest
python update.py --repo yourname/yourapp 1.1.0
```

## Maintenance

### Regular Tasks

1. **Monitor Releases**: Review release success rates
2. **Update Dependencies**: Keep Python environment current
3. **Security Audits**: Regular token and permission review
4. **Documentation**: Keep this document current

### Long-term Considerations

1. **Scaling**: Handle multiple repositories
2. **Automation**: CI/CD integration possibilities
3. **Monitoring**: Centralized logging and alerting
4. **Enhancements**: Feature requests and improvements

---

This system provides a robust, secure, and maintainable solution for Python application updates. The architecture balances simplicity with comprehensive functionality, ensuring reliable deployment across various environments.