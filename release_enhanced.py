#!/usr/bin/env python3
"""
Enhanced release script for creating comprehensive multi-platform releases.
Analyzes changes with advanced version detection, creates structured releases,
and deploys to target repositories with GitHub Actions integration.
Uses only standard Python libraries.
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import zipfile
import tempfile
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import hashlib
import re
from datetime import datetime
from dotenv import load_dotenv


import version
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("Warning: PyYAML not available. YAML workflows will be skipped.")

load_dotenv()


class AdvancedVersionDetector:
    """Advanced version detection using multiple methods with fallback options."""
    
    def __init__(self, repo_root: str = "."):
        """
        Initialize advanced version detector.
        
        Args:
            repo_root: Root directory of the git repository
        """
        self.repo_root = Path(repo_root)
        self.config_file = self.repo_root / "release_config.json"
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load release configuration from file or environment variables.
        
        Returns:
            Configuration dictionary
        """
        config = {
            "exclude_patterns": [
                ".git", "__pycache__", "*.pyc", ".idea", ".vscode", 
                "node_modules", "build", "dist", ".DS_Store", "Thumbs.db"
            ],
            "version_sources": ["file_changes", "commits", "config"],
            "breaking_change_patterns": [
                "BREAKING CHANGE:", "breaking:", "!:", "major change",
                "deprecat", "remove", "delete", "schema", "migration"
            ],
            "feature_patterns": [
                "feat:", "feature:", "new", "add", "implement", "create",
                "module", "component", "service"
            ],
            "fix_patterns": [
                "fix:", "bugfix:", "patch:", "resolve", "correct", "update"
            ]
        }
        
        # Load from config file if exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    config.update(file_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
        
        # Override with environment variables
        if 'RELEASE_EXCLUDE_PATTERNS' in os.environ:
            config['exclude_patterns'] = os.environ['RELEASE_EXCLUDE_PATTERNS'].split(',')
        if 'GITHUB_TOKEN' in os.environ:
            config['github_token'] = os.environ['GITHUB_TOKEN']
        if 'TARGET_REPO_TOKEN' in os.environ:
            config['target_repo_token'] = os.environ['TARGET_REPO_TOKEN']
        
        return config
    
    def analyze_commit_messages(self, since_tag: Optional[str] = None) -> Dict[str, int]:
        """
        Analyze commit messages for version indicators.
        
        Args:
            since_tag: Tag to analyze commits since (None means all commits)
            
        Returns:
            Dictionary with counts of each type (major, minor, patch)
        """
        counts = {"major": 0, "minor": 0, "patch": 0}
        config = self.load_config()
        
        try:
            if since_tag:
                cmd = ["git", "log", f"{since_tag}..HEAD", "--oneline"]
            else:
                cmd = ["git", "log", "--oneline"]
            
            result = subprocess.run(
                cmd, cwd=self.repo_root, capture_output=True, 
                text=True, check=True, timeout=30
            )
            
            commits = result.stdout.strip().split('\n')
            
            for commit in commits:
                commit_lower = commit.lower()
                
                # Check for breaking changes
                for pattern in config['breaking_change_patterns']:
                    if pattern in commit_lower:
                        counts["major"] += 1
                        break
                else:
                    # Check for features
                    for pattern in config['feature_patterns']:
                        if pattern in commit_lower:
                            counts["minor"] += 1
                            break
                    else:
                        # Check for fixes
                        for pattern in config['fix_patterns']:
                            if pattern in commit_lower:
                                counts["patch"] += 1
                                break
            
        except subprocess.CalledProcessError as e:
            print(f"Error analyzing commits: {e}")
        except Exception as e:
            print(f"Unexpected error analyzing commits: {e}")
        
        return counts
    
    def determine_version_bump_advanced(self, added_files: Set[str], modified_files: Set[str], 
                                     deleted_files: Set[str], since_tag: Optional[str] = None) -> str:
        """
        Determine version bump using multiple analysis methods with fallback.
        
        Args:
            added_files: Set of added files
            modified_files: Set of modified files  
            deleted_files: Set of deleted files
            since_tag: Previous tag to analyze from
            
        Returns:
            'major', 'minor', or 'patch'
        """
        config = self.load_config()
        
        # Method 1: File-based analysis (primary)
        file_bump = self._analyze_file_changes(added_files, modified_files, deleted_files, config)
        
        # Method 2: Commit message analysis (secondary)
        commit_counts = self.analyze_commit_messages(since_tag)
        commit_bump = max(commit_counts.items(), key=lambda x: x[1])[0] if any(commit_counts.values()) else 'patch'
        
        # Method 3: Configuration override (if specified)
        config_bump = None
        if 'force_version_type' in config:
            config_bump = config['force_version_type']
        
        # Decision logic with priority
        if config_bump:
            print(f"Using configured version bump: {config_bump}")
            return config_bump
        
        # Prioritize file analysis over commit analysis
        if file_bump == 'major' or commit_counts['major'] > 0:
            print(f"Major version bump detected (file analysis: {file_bump}, commit analysis: {commit_counts})")
            return 'major'
        elif file_bump == 'minor' or commit_counts['minor'] > 0:
            print(f"Minor version bump detected (file analysis: {file_bump}, commit analysis: {commit_counts})")
            return 'minor'
        else:
            print(f"Patch version bump detected (file analysis: {file_bump}, commit analysis: {commit_counts})")
            return 'patch'
    
    def _analyze_file_changes(self, added_files: Set[str], modified_files: Set[str], 
                            deleted_files: Set[str], config: Dict[str, Any]) -> str:
        """
        Analyze file changes for version indicators.
        
        Args:
            added_files: Set of added files
            modified_files: Set of modified files
            deleted_files: Set of deleted files
            config: Configuration dictionary
            
        Returns:
            'major', 'minor', or 'patch'
        """
        all_changed = added_files | modified_files | deleted_files
        
        # Check for major indicators
        major_indicators = config.get('major_indicators', [
            'config', 'database', 'schema', 'migrate', 'requirements.txt', 
            'setup.py', 'pyproject.toml', 'Dockerfile', 'docker-compose'
        ])
        
        for file_path in all_changed:
            file_path_lower = file_path.lower()
            for indicator in major_indicators:
                if indicator in file_path_lower:
                    print(f"Major indicator in file: {file_path}")
                    return 'major'
        
        # Check for minor indicators (new files)
        if added_files:
            minor_indicators = config.get('minor_indicators', [
                'module', 'feature', 'component', 'service', 'handler'
            ])
            
            for file_path in added_files:
                file_path_lower = file_path.lower()
                for indicator in minor_indicators:
                    if indicator in file_path_lower:
                        print(f"Minor indicator in file: {file_path}")
                        return 'minor'
            
            # Any new file suggests minor version
            if len(added_files) > 0:
                print(f"Minor version suggested by {len(added_files)} new files")
                return 'minor'
        
        # Default to patch for modifications
        if modified_files:
            print(f"Patch version suggested by {len(modified_files)} modified files")
            return 'patch'
        
        return 'patch'


class StructuredReleaseCreator:
    """Creates structured release packages with multi-platform support."""
    
    def __init__(self, repo_root: str = "."):
        """
        Initialize structured release creator.
        
        Args:
            repo_root: Root directory of the git repository
        """
        self.repo_root = Path(repo_root)
        self.detector = AdvancedVersionDetector(repo_root)
        self.config = self.detector.load_config()
    
    def create_release_structure(self, version_str: str, temp_dir: Path,
                               added_files: Set[str], modified_files: Set[str],
                               deleted_files: Set[str]) -> bool:
        """
        Create the structured release folder hierarchy.
        
        Args:
            version_str: Version string (e.g., "1.2.3")
            temp_dir: Temporary directory to work in
            added_files: Set of added files
            modified_files: Set of modified files
            deleted_files: Set of deleted files
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create main release folder
            release_folder = temp_dir / f"release_v{version_str}"
            release_folder.mkdir(exist_ok=True)
            
            # Create subdirectories
            codebase_dir = release_folder / "codebase" / "code"
            platform_dir = release_folder / "platform"
            manifest_dir = release_folder / "manifest"
            
            codebase_dir.mkdir(parents=True, exist_ok=True)
            platform_dir.mkdir(parents=True, exist_ok=True)
            manifest_dir.mkdir(parents=True, exist_ok=True)
            
            # Create platform subdirectories
            (platform_dir / "windows").mkdir(exist_ok=True)
            (platform_dir / "linux").mkdir(exist_ok=True)
            (platform_dir / "mac").mkdir(exist_ok=True)
            
            # Copy codebase excluding specified patterns
            self._copy_codebase(codebase_dir)
            
            # Create platform-specific packages
            self._create_platform_packages(platform_dir, version_str)
            
            # Create enhanced manifest
            self._create_enhanced_manifest(manifest_dir, version_str, added_files, modified_files, deleted_files)
            
            # Create GitHub Actions workflow
            self._create_github_actions_workflow(manifest_dir, version_str)
            
            print(f"Created release structure at: {release_folder}")
            return True
            
        except Exception as e:
            print(f"Error creating release structure: {e}")
            return False
    
    def _copy_codebase(self, codebase_dir: Path) -> None:
        """
        Copy codebase to release directory, excluding specified patterns.
        
        Args:
            codebase_dir: Target directory for codebase
        """
        exclude_patterns = self.config.get('exclude_patterns', [])
        
        for root, dirs, files in os.walk(self.repo_root):
            # Modify dirs in-place to prevent walking excluded directories
            dirs[:] = [d for d in dirs if not any(
                pattern.startswith('.') and d.startswith('.') or
                pattern in d for pattern in exclude_patterns
            )]
            
            for file in files:
                # Skip files matching exclude patterns
                if any(file.endswith(pattern.lstrip('*')) or pattern in file 
                       for pattern in exclude_patterns if '*' in pattern):
                    continue
                
                src_path = Path(root) / file
                rel_path = src_path.relative_to(self.repo_root)
                dst_path = codebase_dir / rel_path
                
                # Ensure parent directory exists
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    shutil.copy2(src_path, dst_path)
                except Exception as e:
                    print(f"Warning: Could not copy {src_path}: {e}")
    
    def _create_platform_packages(self, platform_dir: Path, version_str: str) -> None:
        """
        Create platform-specific packages (placeholder for CI/CD integration).
        
        Args:
            platform_dir: Platform directory root
            version_str: Version string
        """
        platforms = ["windows", "linux", "mac"]
        
        for platform in platforms:
            platform_path = platform_dir / platform
            
            # Create placeholder zip files that will be replaced by CI/CD
            placeholder_content = {
                "platform": platform,
                "version": version_str,
                "status": "pending_build",
                "created_by": "release_enhanced.py",
                "build_instructions": [
                    f"This package will be built automatically by GitHub Actions",
                    f"Platform: {platform}",
                    f"Version: {version_str}",
                    "Build the application and create a zip file",
                    "Replace this placeholder with the actual build artifact"
                ]
            }
            
            # Create placeholder zip
            placeholder_file = platform_path / f"{platform}_v{version_str}_placeholder.json"
            with open(placeholder_file, 'w') as f:
                json.dump(placeholder_content, f, indent=2)
            
            # Create empty zip that CI/CD will populate
            zip_path = platform_path / f"app_{platform}_v{version_str}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zf:
                # Add just the placeholder info for now
                zf.writestr("build_info.json", json.dumps(placeholder_content, indent=2))
    
    def _create_enhanced_manifest(self, manifest_dir: Path, version_str: str,
                                added_files: Set[str], modified_files: Set[str],
                                deleted_files: Set[str]) -> None:
        """
        Create enhanced manifest with comprehensive metadata.
        
        Args:
            manifest_dir: Manifest directory
            version_str: Version string
            added_files: Set of added files
            modified_files: Set of modified files
            deleted_files: Set of deleted files
        """
        # Get git history for changelog and previous version
        previous_version = None
        try:
            last_tag_result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=self.repo_root, capture_output=True, text=True
            )
            last_tag = last_tag_result.stdout.strip() if last_tag_result.returncode == 0 else None
            previous_version = last_tag if last_tag else None
            
            if last_tag:
                log_result = subprocess.run(
                    ["git", "log", f"{last_tag}..HEAD", "--oneline"],
                    cwd=self.repo_root, capture_output=True, text=True
                )
                changelog = log_result.stdout.strip().split('\n') if log_result.returncode == 0 else []
            else:
                log_result = subprocess.run(
                    ["git", "log", "--oneline"],
                    cwd=self.repo_root, capture_output=True, text=True
                )
                changelog = log_result.stdout.strip().split('\n') if log_result.returncode == 0 else []
        except Exception as e:
            print(f"Warning: Could not generate changelog: {e}")
            changelog = []
        
        manifest = {
            "version": version_str,
            "previous_version": previous_version,
            "build_date": datetime.now().isoformat(),
            "created_by": "release_enhanced.py",
            "changelog": changelog,
            "platforms": {
                "windows": {
                    "supported": True,
                    "architecture": ["x64"],
                    "requirements": ["Windows 10+"],
                    "file_name": f"app_windows_v{version_str}.zip",
                    "download_url": f"PLATFORM_RELEASE_URL_WINDOWS",
                    "file_size": "TBD",
                    "checksum": "TBD"
                },
                "linux": {
                    "supported": True,
                    "architecture": ["x64"],
                    "requirements": ["Ubuntu 18.04+", "CentOS 7+"],
                    "file_name": f"app_linux_v{version_str}.zip",
                    "download_url": f"PLATFORM_RELEASE_URL_LINUX",
                    "file_size": "TBD",
                    "checksum": "TBD"
                },
                "mac": {
                    "supported": True,
                    "architecture": ["x64", "arm64"],
                    "requirements": ["macOS 10.14+"],
                    "file_name": f"app_mac_v{version_str}.zip",
                    "download_url": f"PLATFORM_RELEASE_URL_MAC",
                    "file_size": "TBD",
                    "checksum": "TBD"
                }
            },
            "codebase": {
                "directory": "codebase/code",
                "total_files": "TBD",
                "languages": ["Python"],
                "dependencies": "See requirements.txt in codebase",
                "files_add": list(added_files),
                "files_edit": list(modified_files),
                "files_delete": list(deleted_files)
            },
            "release_notes": self._generate_release_notes(changelog),
            "installation_instructions": {
                "windows": "1. Download app_windows_v{version}.zip\n2. Extract to desired location\n3. Run app.exe",
                "linux": "1. Download app_linux_v{version}.zip\n2. Extract: unzip app_linux_v{version}.zip\n3. Run: ./app",
                "mac": "1. Download app_mac_v{version}.zip\n2. Double-click to extract\n3. Run app from Applications"
            }
        }
        
        with open(manifest_dir / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)
    
    def _create_github_actions_workflow(self, manifest_dir: Path, version_str: str) -> None:
        """
        Create GitHub Actions workflow for platform builds.
        
        Args:
            manifest_dir: Manifest directory
            version_str: Version string
        """
        workflow = {
            "name": f"Build Release v{version_str}",
            "on": {
                "push": {
                    "branches": ["main"],
                    "paths": [
                        "release_v{version_str}/**"
                    ]
                },
                "workflow_dispatch": {
                    "inputs": {
                        "version": {
                            "description": "Release version",
                            "required": True,
                            "default": version_str
                        },
                        "force_rebuild": {
                            "description": "Force rebuild all platforms",
                            "required": False,
                            "type": "boolean"
                        }
                    }
                }
            },
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "strategy": {
                        "matrix": {
                            "platform": ["windows", "linux", "mac"]
                        }
                    },
                    "steps": [
                        {
                            "name": "Checkout code",
                            "uses": "actions/checkout@v3"
                        },
                        {
                            "name": "Setup Node.js", 
                            "uses": "actions/setup-node@v3",
                            "with": {"node-version": "18"}
                        },
                        {
                            "name": "Setup Python",
                            "uses": "actions/setup-python@v4",
                            "with": {"python-version": "3.9"}
                        },
                        {
                            "name": "Build for ${{ matrix.platform }}",
                            "run": """
                                echo "Building for ${{ matrix.platform }}"
                                # Add your build commands here
                                # Example:
                                # if [ "${{ matrix.platform }}" = "windows" ]; then
                                #   # Windows build commands
                                # elif [ "${{ matrix.platform }}" = "linux" ]; then
                                #   # Linux build commands
                                # else
                                #   # macOS build commands
                                # fi
                                
                                # Create platform-specific zip
                                mkdir -p dist/${{ matrix.platform }}
                                # Your build output goes here
                                # cp your-build-output dist/${{ matrix.platform }}/
                                
                                # For now, create placeholder
                                echo '{{"platform": "${{ matrix.platform }}", "version": "{version}", "status": "built"}}' > dist/${{ matrix.platform }}/build_info.json
                                
                                # Create zip
                                cd dist/${{ matrix.platform }}
                                zip -r ../../app_${{ matrix.platform }}_v{version}.zip .
                            """.format(version=version_str)
                        },
                        {
                            "name": "Create Release",
                            "id": "create_release",
                            "uses": "actions/create-release@v1",
                            "env": {
                                "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
                            },
                            "with": {
                                "tag_name": "v{version}",
                                "release_name": "Release v{version}",
                                "draft": False,
                                "prerelease": False
                            }
                        },
                        {
                            "name": "Upload Release Asset",
                            "uses": "actions/upload-release-asset@v1",
                            "env": {
                                "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
                            },
                            "with": {
                                "upload_url": "${{ steps.create_release.outputs.upload_url }}",
                                "asset_path": "./app_${{ matrix.platform }}_v{version}.zip",
                                "asset_name": "app_${{ matrix.platform }}_v{version}.zip",
                                "asset_content_type": "application/zip"
                            }
                        }
                    ]
                },
                "update_manifest": {
                    "needs": "build",
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {
                            "name": "Update Manifest URLs",
                            "run": """
                                # Update manifest.json with actual download URLs
                                # and file sizes, checksums after build completes
                                echo "Updating manifest with build results..."
                            """
                        }
                    ]
                }
            }
        }
        
        # Save as .yml file
        workflow_dir = manifest_dir / "github_actions"
        workflow_dir.mkdir(exist_ok=True)
        
        with open(workflow_dir / "build_release.yml", 'w') as f:
            if YAML_AVAILABLE:
                yaml.dump(workflow, f, default_flow_style=False)
            else:
                # Fallback to JSON if YAML not available
                import json
                json.dump(workflow, f, indent=2)
    
    def _generate_release_notes(self, changelog: List[str]) -> str:
        """
        Generate release notes from changelog.
        
        Args:
            changelog: List of commit messages
            
        Returns:
            Formatted release notes
        """
        if not changelog:
            return "Initial release."
        
        notes = "# Release Notes\n\n"
        
        added = []
        changed = []
        fixed = []
        
        for commit in changelog:
            commit_lower = commit.lower()
            if any(word in commit_lower for word in ['add', 'new', 'create']):
                added.append(commit)
            elif any(word in commit_lower for word in ['fix', 'bug', 'patch']):
                fixed.append(commit)
            else:
                changed.append(commit)
        
        if added:
            notes += "## Added\n"
            for commit in added:
                notes += f"- {commit}\n"
            notes += "\n"
        
        if changed:
            notes += "## Changed\n"
            for commit in changed:
                notes += f"- {commit}\n"
            notes += "\n"
        
        if fixed:
            notes += "## Fixed\n"
            for commit in fixed:
                notes += f"- {commit}\n"
            notes += "\n"
        
        return notes


class TargetRepositoryDeployer:
    """Handles deployment to target GitHub repository."""
    
    def __init__(self, source_repo_root: str = "."):
        """
        Initialize target repository deployer.
        
        Args:
            source_repo_root: Source repository root directory
        """
        self.source_repo_root = Path(source_repo_root)
        self.detector = AdvancedVersionDetector(source_repo_root)
        self.config = self.detector.load_config()
    
    def deploy_to_target_repo(self, temp_dir: Path, target_repo: str,
                            version_str: str) -> bool:
        """
        Deploy release structure to target repository.
        
        Args:
            temp_dir: Temporary directory containing release structure
            target_repo: Target repository in format owner/name
            version_str: Version string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get tokens
            source_token = self.config.get('github_token', os.getenv('GITHUB_TOKEN'))
            target_token = self.config.get('target_repo_token', os.getenv('TARGET_REPO_TOKEN', source_token))
            
            if not target_token:
                print("Error: Target repository token not provided")
                return False
            
            owner, repo = target_repo.split('/')
            
            # Create temporary clone for target repo
            with tempfile.TemporaryDirectory() as temp_clone_dir:
                target_repo_path = Path(temp_clone_dir) / repo
                target_repo_path.mkdir(parents=True)
                
                # Clone target repo
                clone_url = f"https://github.com/{owner}/{repo}.git"
                subprocess.run([
                    "git", "clone", clone_url, str(target_repo_path)
                ], check=True, timeout=120)
                
                # Create release branch
                branch_name = f"release/v{version_str}"
                subprocess.run([
                    "git", "checkout", "-b", branch_name
                ], cwd=target_repo_path, check=True)
                
                # Copy release files to target repo
                target_release_dir = target_repo_path / f"release_v{version_str}"
                if target_release_dir.exists():
                    shutil.rmtree(target_release_dir)
                source_release_dir = temp_dir / f"release_v{version_str}"
                shutil.copytree(source_release_dir, target_release_dir)
                
                # Commit and push
                subprocess.run(["git", "add", "."], cwd=target_repo_path, check=True)
                subprocess.run([
                    "git", "commit", "-m", f"Release v{version_str} deployment"
                ], cwd=target_repo_path, check=True)
                
                subprocess.run([
                    "git", "push", "-u", "origin", branch_name
                ], cwd=target_repo_path, check=True)
                
                # Create pull request (optional)
                self._create_pull_request(owner, repo, branch_name, version_str, target_token)
            
            print(f"Successfully deployed to target repository: {target_repo}")
            return True
            
        except Exception as e:
            print(f"Error deploying to target repository: {e}")
            return False
    
    def _create_pull_request(self, owner: str, repo: str, branch_name: str, 
                          version_str: str, token: str) -> None:
        """
        Create pull request for release deployment.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch_name: Branch name
            version_str: Version string
            token: GitHub token
        """
        try:
            # This would typically use GitHub API to create PR
            # For now, just log the action
            print(f"Pull request should be created for branch: {branch_name}")
            print(f"Repository: {owner}/{repo}")
            print(f"Version: {version_str}")
        except Exception as e:
            print(f"Warning: Could not create pull request: {e}")


class EnhancedReleaseManager:
    """Enhanced release manager combining all advanced features."""
    
    def __init__(self, repo_root: str = "."):
        """
        Initialize enhanced release manager.
        
        Args:
            repo_root: Root directory of the repository
        """
        self.repo_root = Path(repo_root)
        self.detector = AdvancedVersionDetector(repo_root)
        self.structure_creator = StructuredReleaseCreator(repo_root)
        self.deployer = TargetRepositoryDeployer(repo_root)
        self.config = self.detector.load_config()
    
    def create_enhanced_release(self, source_repo: str, target_repo: Optional[str] = None,
                             target_version: Optional[str] = None) -> bool:
        """
        Create enhanced multi-platform release.
        
        Args:
            source_repo: Source repository in format owner/name
            target_repo: Target repository for deployment (optional)
            target_version: Target version (auto-detected if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print("Starting enhanced release creation...")
            
            # Get current version from source repo
            current_version = version.Version("1.0.0")  # Default
            version_file = self.repo_root / "version.json"
            if version_file.exists():
                with open(version_file, 'r') as f:
                    data = json.load(f)
                    current_version = version.Version(data['version'])
            
            # Analyze changes for version bump
            source_owner, source_name = source_repo.split('/')
            added_files, modified_files, deleted_files = self._analyze_source_changes()
            
            if not (added_files or modified_files or deleted_files):
                print("No changes detected since last release")
                return True
            
            # Determine version bump using advanced detection
            bump_type = self.detector.determine_version_bump_advanced(
                added_files, modified_files, deleted_files
            )
            
            # Calculate new version
            if target_version:
                new_version = version.Version(target_version)
            else:
                if bump_type == 'major':
                    new_version = current_version.bump_major()
                elif bump_type == 'minor':
                    new_version = current_version.bump_minor()
                else:
                    new_version = current_version.bump_patch()
            
            version_str = str(new_version)
            print(f"Creating enhanced release: {current_version} -> {new_version} ({bump_type})")
            
            # Create release structure
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                if not self.structure_creator.create_release_structure(version_str, temp_path, added_files, modified_files, deleted_files):
                    return False
                
                # Update source repository files
                self._update_source_files(new_version, added_files, modified_files, deleted_files)
                
                # Deploy to target repository if specified
                if target_repo:
                    if not self.deployer.deploy_to_target_repo(temp_path, target_repo, version_str):
                        print("Warning: Deployment to target repository failed")
                
                print(f"Enhanced release {version_str} completed successfully!")
                return True
            
        except Exception as e:
            print(f"Error in enhanced release: {e}")
            return False
    
    def _analyze_source_changes(self) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Analyze changes in source repository since last release.
        
        Returns:
            Tuple of (added_files, modified_files, deleted_files)
        """
        added_files = set()
        modified_files = set()
        deleted_files = set()
        
        try:
            # Get last tag if available
            last_tag_result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=self.repo_root, capture_output=True, text=True
            )
            
            if last_tag_result.returncode == 0:
                last_tag = last_tag_result.stdout.strip()
                # Get diff since last tag
                diff_result = subprocess.run(
                    ["git", "diff", "--name-status", f"{last_tag}..HEAD"],
                    cwd=self.repo_root, capture_output=True, text=True, check=True
                )
            else:
                # No tags found, get all files in the repository
                diff_result = subprocess.run(
                    ["git", "ls-files"],
                    cwd=self.repo_root, capture_output=True, text=True, check=True
                )
                # Mark all as added for initial release
                for line in diff_result.stdout.strip().split('\n'):
                    if line.strip():
                        added_files.add(line.strip())
                return added_files, modified_files, deleted_files
            
            # Parse git diff output
            for line in diff_result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    status, file_path = parts[0], parts[1]
                    if status == 'A':  # Added
                        added_files.add(file_path)
                    elif status == 'M':  # Modified
                        modified_files.add(file_path)
                    elif status == 'D':  # Deleted
                        deleted_files.add(file_path)
                    elif status == 'R':  # Renamed (old_path new_path)
                        if len(parts) >= 3:
                            old_path, new_path = parts[1], parts[2]
                            deleted_files.add(old_path)
                            added_files.add(new_path)
            
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not analyze changes: {e}")
        except Exception as e:
            print(f"Warning: Unexpected error analyzing changes: {e}")
        
        return added_files, modified_files, deleted_files
    
    def _update_source_files(self, version: version.Version, added_files: Set[str], 
                           modified_files: Set[str], deleted_files: Set[str]) -> None:
        """
        Update source repository files with new version info.
        
        Args:
            version: New version
            added_files: Added files
            modified_files: Modified files
            deleted_files: Deleted files
        """
        # Update version.json
        version_data = {
            "version": str(version),
            "build_date": datetime.now().isoformat(),
            "description": f"Release {version}"
        }
        
        with open(self.repo_root / "version.json", 'w') as f:
            json.dump(version_data, f, indent=2)
        
        # Create manifest for source repo
        manifest = {
            "version": str(version),
            "files_add": list(added_files),
            "files_edit": list(modified_files), 
            "files_delete": list(deleted_files),
            "build_date": datetime.now().isoformat()
        }
        
        with open(self.repo_root / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)


def main():
    """Main entry point for enhanced release script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create enhanced multi-platform release")
    parser.add_argument("--source-repo", required=True, 
                       help="Source repository in format owner/name")
    parser.add_argument("--target-repo", 
                       help="Target repository for deployment (optional)")
    parser.add_argument("--version", help="Target version (auto-detected if None)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    if "/" not in args.source_repo:
        print("Source repository must be in format owner/name")
        sys.exit(1)
    
    if args.dry_run:
        print("DRY RUN MODE - No actual changes will be made")
        print(f"Source repo: {args.source_repo}")
        if args.target_repo:
            print(f"Target repo: {args.target_repo}")
        print(f"Version: {'auto' if not args.version else args.version}")
        return
    
    # Create enhanced release
    manager = EnhancedReleaseManager()
    success = manager.create_enhanced_release(
        args.source_repo, args.target_repo, args.version
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()



