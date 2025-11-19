# Enhanced Multi-Platform Release System

This guide describes the enhanced release system that provides advanced multi-platform deployment capabilities with automated GitHub Actions integration.

## Overview

The enhanced release system (`release_enhanced.py`) extends the basic update mechanism with:

- **Advanced Version Detection**: Multiple analysis methods with fallback options
- **Multi-Platform Support**: Windows, Linux, and macOS builds
- **Structured Release Packages**: Organized folder structure for codebase, platforms, and manifests
- **GitHub Actions Integration**: Automated builds and deployments
- **Target Repository Deployment**: Deploy to separate repository for distribution

## Files Overview

### Core Scripts
- **`release_enhanced.py`** - Enhanced release script with advanced features
- **`release.py`** - Original basic release script
- **`release_config.json`** - Configuration file for release settings
- **`github_actions_build.yml`** - GitHub Actions workflow for platform builds

### Supporting Files
- **`version.py`** - Version utility module
- **`update.py`** - User-side update script
- **`version.json`** - Current version tracking
- **`manifest.json`** - Release manifest

## Advanced Features

### 1. Enhanced Version Detection

The system uses multiple methods to determine version bumps:

#### File-Based Analysis (Primary)
```json
{
  "major_indicators": ["config", "database", "schema", "migration"],
  "minor_indicators": ["module", "feature", "component", "service"],
  "breaking_change_patterns": ["BREAKING CHANGE:", "deprecat", "remove"]
}
```

#### Commit Message Analysis (Secondary)
- Detects conventional commit patterns
- Looks for `feat:`, `fix:`, `BREAKING CHANGE:`
- Counts each type for decision making

#### Configuration Override (Tertiary)
- Force specific version type via config file
- Environment variable overrides

### 2. Multi-Platform Release Structure

Each release creates the following structure:

```
release_v1.2.3/
├── codebase/
│   └── code/
│       ├── All source files (excluding configured patterns)
│       ├── requirements.txt
│       ├── version.json
│       └── ... (other application files)
├── platform/
│   ├── windows/
│   │   ├── app_windows_v1.2.3.zip
│   │   └── build_info.json
│   ├── linux/
│   │   ├── app_linux_v1.2.3.zip
│   │   └── build_info.json
│   └── mac/
│       ├── app_mac_v1.2.3.zip
│       └── build_info.json
└── manifest/
    ├── manifest.json
    ├── github_actions/
    │   └── build_release.yml
    └── release_notes.md
```

### 3. GitHub Actions Integration

The automated workflow includes:

#### Build Jobs
- **Detect Release**: Identify version and platforms to build
- **Build Platforms**: Parallel builds for Windows, Linux, macOS
- **Update Manifest**: Update manifest with build results
- **Create Release**: Publish GitHub release with assets

#### Features
- Caching for faster builds
- Artifact retention
- Failure handling
- Notifications

## Usage

### Basic Usage

```bash
# Create enhanced release with auto-detection
python release_enhanced.py --source-repo owner/app

# Deploy to target repository
python release_enhanced.py --source-repo owner/app --target-repo owner/app-releases

# Specify version manually
python release_enhanced.py --source-repo owner/app --version 1.2.3

# Dry run to preview
python release_enhanced.py --source-repo owner/app --dry-run
```

### Environment Setup

#### Required Environment Variables
```bash
# GitHub token for source repo access
export GITHUB_TOKEN=your_github_token

# Token for target repo (can be same as above)
export TARGET_REPO_TOKEN=your_target_repo_token

# Exclude patterns (optional)
export RELEASE_EXCLUDE_PATTERNS=.git,__pycache__,*.pyc
```

#### Configuration
Create `release_config.json` to customize behavior:

```json
{
  "exclude_patterns": [".git", "__pycache__", "*.pyc"],
  "breaking_change_patterns": ["BREAKING CHANGE:", "deprecat"],
  "platform_config": {
    "windows": {
      "requirements": ["Windows 10+"],
      "executable": "app.exe"
    }
  }
}
```

## GitHub Actions Setup

### 1. Repository Structure

1. **Source Repository**: Contains your application code
2. **Target Repository**: (Optional) For distribution and releases

### 2. Workflow Setup

1. Copy `github_actions_build.yml` to `.github/workflows/`
2. Configure repository secrets:
   - `GITHUB_TOKEN`: Automatic (provided by GitHub)
   - Additional tokens for external services

### 3. Workflow Triggers

The workflow triggers on:
- Push to main branch with release folder changes
- Pull requests with release changes
- Manual dispatch with specified version

## Advanced Configuration

### Version Detection Configuration

```json
{
  "version_sources": ["file_changes", "commits", "config"],
  "force_version_type": "minor",  // Override auto-detection
  "breaking_change_patterns": [
    "BREAKING CHANGE:",
    "deprecat",
    "remove"
  ]
}
```

### Platform Configuration

```json
{
  "platform_config": {
    "windows": {
      "supported": true,
      "architectures": ["x64"],
      "requirements": ["Windows 10+"]
    },
    "linux": {
      "supported": true,
      "build_tools": ["python", "docker"]
    }
  }
}
```

### Build Configuration

```json
{
  "build_config": {
    "timeout_minutes": 30,
    "parallel_builds": true,
    "cache_dependencies": true,
    "artifacts_retention_days": 30
  }
}
```

## Integration Guide

### 1. Initial Setup

```bash
# 1. Configure repository
git init
git add .
git commit -m "Initial setup"

# 2. Create configuration
cp release_config.json.example release_config.json
# Edit release_config.json as needed

# 3. Set up GitHub Actions
mkdir -p .github/workflows
cp github_actions_build.yml .github/workflows/
```

### 2. First Release

```bash
# Create initial release
python release_enhanced.py --source-repo yourname/yourapp --version 1.0.0

# This creates:
# - release_v1.0.0/ folder structure
# - Updated version files
# - GitHub Actions workflow
# - Enhanced manifest
```

### 3. Subsequent Releases

```bash
# Make code changes
git add .
git commit -m "feat: Add new user authentication module"

# Create release (auto-detects minor version bump)
python release_enhanced.py --source-repo yourname/yourapp
```

### 4. Target Repository Deployment

```bash
# Deploy to distribution repository
python release_enhanced.py \
  --source-repo yourname/yourapp \
  --target-repo yourname/yourapp-releases
```

## Troubleshooting

### Common Issues

#### 1. Version Detection Not Working
```bash
# Check configuration
python -c "import json; print(json.load(open('release_config.json')))"

# Analyze commits manually
git log --oneline | head -10
```

#### 2. GitHub Actions Not Triggering
- Ensure workflow file is in `.github/workflows/`
- Check file name format (`.yml` or `.yaml`)
- Verify repository permissions

#### 3. Build Failures
- Check platform-specific build logic
- Verify dependencies are installed
- Review build logs in Actions tab

### Debug Mode

Enable verbose logging:
```bash
export DEBUG_RELEASE=true
python release_enhanced.py --dry-run --source-repo yourname/yourapp
```

## Best Practices

### 1. Configuration Management
- Use environment-specific configs
- Keep sensitive data in environment variables
- Version control your config files

### 2. Release Process
- Always use dry-run first
- Test in staging environment
- Monitor GitHub Actions runs

### 3. Platform Support
- Test builds on each platform
- Include platform-specific dependencies
- Document platform requirements

### 4. Security
- Use least-privilege tokens
- Rotate tokens regularly
- Scan for security vulnerabilities

## Examples

### Example 1: Breaking Change Release

```bash
# Make breaking changes (database schema)
git add .
git commit -m "feat!: Update user table schema"

# Release (auto-detects major bump)
python release_enhanced.py --source-repo yourname/yourapp
# Output: 1.2.3 → 2.0.0 (major)
```

### Example 2: Bug Fix Release

```bash
# Fix bug
git add .
git commit -m "fix: Resolve login authentication issue"

# Release (auto-detects patch bump)
python release_enhanced.py --source-repo yourname/yourapp  
# Output: 1.2.3 → 1.2.4 (patch)
```

### Example 3: Custom Configuration

```json
{
  "force_version_type": "minor",
  "exclude_patterns": [".git", "tests", "docs"],
  "platform_config": {
    "windows": {"supported": false},
    "linux": {"supported": true}
  }
}
```

## Migration from Basic Release

### From Basic to Enhanced

1. **Backup Current Setup**
   ```bash
   cp release.py release_backup.py
   cp manifest.json manifest_backup.json
   ```

2. **Install Enhanced System**
   ```bash
   cp release_enhanced.py release.py  # Replace if desired
   cp release_config.json.example release_config.json
   ```

3. **Update Configuration**
   - Customize `release_config.json`
   - Set environment variables
   - Configure GitHub Actions

4. **Test Migration**
   ```bash
   python release_enhanced.py --dry-run --source-repo yourname/yourapp
   ```

## Performance Considerations

### Optimization Tips

1. **Build Caching**
   - Enable dependency caching in workflows
   - Use artifact retention effectively
   - Cache build tools

2. **Parallel Processing**
   - Build platforms in parallel
   - Use matrix strategies
   - Optimize build scripts

3. **Network Optimization**
   - Use GitHub's caching
   - Compress artifacts
   - Optimize git operations

## Support and Maintenance

### Regular Maintenance
- Update dependencies regularly
- Review GitHub Actions versions
- Monitor build success rates
- Update documentation

### Getting Help
- Check GitHub Actions logs
- Review configuration files
- Test with dry-run mode
- Check issue trackers

---

This enhanced release system provides a comprehensive solution for multi-platform application deployment with advanced version detection and automated CI/CD integration.