#!/usr/bin/env python3
"""
Developer-side release script for creating new application releases.
Analyzes changes, determines version bump, creates manifest, and uploads to GitHub.
Uses only standard Python libraries.
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import hashlib

import version


class ChangeAnalyzer:
    """Analyzes git changes to determine version bump type and file changes."""
    
    def __init__(self, repo_root: str = "."):
        """
        Initialize change analyzer.
        
        Args:
            repo_root: Root directory of the git repository
        """
        self.repo_root = Path(repo_root)
    
    def get_last_release_tag(self) -> Optional[str]:
        """
        Get the most recent release tag from git.
        
        Returns:
            Last release tag or None if not found
        """
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            # No tags found
            return None
    
    def get_changed_files_since_last_release(self) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Get list of files changed since last release.
        
        Returns:
            Tuple of (added_files, modified_files, deleted_files)
        """
        try:
            # Verify we're in a git repository
            if not (self.repo_root / ".git").exists():
                print("Error: Not in a git repository")
                return set(), set(), set()
            
            last_tag = self.get_last_release_tag()
            if not last_tag:
                print("No previous release found - analyzing all files")
                # No previous release, consider all files as added
                all_files = set()
                try:
                    for root, dirs, files in os.walk(self.repo_root):
                        # Skip .git directory and other system files
                        dirs_to_skip = ['.git', '__pycache__', '.idea', '.vscode', 'node_modules']
                        for dir_to_skip in dirs_to_skip:
                            if dir_to_skip in dirs:
                                dirs.remove(dir_to_skip)
                        
                        for file in files:
                            # Skip hidden files and common build artifacts
                            if file.startswith('.') or file.endswith('.pyc'):
                                continue
                            
                            rel_path = os.path.relpath(os.path.join(root, file), self.repo_root)
                            all_files.add(rel_path)
                except Exception as e:
                    print(f"Error walking directory tree: {e}")
                    return set(), set(), set()
                
                return all_files, set(), set()
            
            # Get changes since last tag
            try:
                result = subprocess.run(
                    ["git", "diff", "--name-status", last_tag, "HEAD"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30  # 30 second timeout
                )
            except subprocess.TimeoutExpired:
                print("Error: Git command timed out")
                return set(), set(), set()
            except subprocess.CalledProcessError as e:
                print(f"Error getting git changes: {e}")
                print(f"Git stderr: {e.stderr}")
                return set(), set(), set()
            
            added = set()
            modified = set()
            deleted = set()
            
            if not result.stdout.strip():
                print("No changes detected in git diff output")
                return set(), set(), set()
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) < 2:
                    continue
                
                status, filepath = parts[0], parts[1]
                
                # Validate filepath for security
                if not self._validate_filepath(filepath):
                    print(f"Warning: Skipping suspicious file path: {filepath}")
                    continue
                
                if status == 'A':
                    added.add(filepath)
                elif status == 'M':
                    modified.add(filepath)
                elif status == 'D':
                    deleted.add(filepath)
            
            return added, modified, deleted
            
        except Exception as e:
            print(f"Unexpected error analyzing changes: {e}")
            return set(), set(), set()
    
    def _validate_filepath(self, filepath: str) -> bool:
        """
        Validate file path for security.
        
        Args:
            filepath: File path to validate
            
        Returns:
            True if safe, False otherwise
        """
        if not filepath:
            return False
        
        # Check for path traversal attempts
        if '..' in filepath or filepath.startswith('/') or '\\' in filepath:
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = ['..', '~', '$env', '%']
        for pattern in suspicious_patterns:
            if pattern in filepath.lower():
                return False
        
        return True
    
    def determine_version_bump(self, added_files: Set[str], modified_files: Set[str], 
                             deleted_files: Set[str]) -> str:
        """
        Determine version bump type based on file changes.
        
        Args:
            added_files: Set of added files
            modified_files: Set of modified files
            deleted_files: Set of deleted files
            
        Returns:
            'major', 'minor', or 'patch'
        """
        all_changed = added_files | modified_files | deleted_files
        
        # Check for major update indicators
        major_indicators = [
            'config', 'database', 'schema', 'migrate',
            'requirements.txt', 'setup.py', 'pyproject.toml'
        ]
        
        for file_path in all_changed:
            file_path_lower = file_path.lower()
            for indicator in major_indicators:
                if indicator in file_path_lower:
                    print(f"Major update detected due to changes in: {file_path}")
                    return 'major'
        
        # Check for minor update indicators (new files)
        if added_files:
            # Look for new modules, features, etc.
            feature_indicators = ['module', 'feature', 'component', 'service']
            for file_path in added_files:
                file_path_lower = file_path.lower()
                for indicator in feature_indicators:
                    if indicator in file_path_lower:
                        print(f"Minor update detected due to new file: {file_path}")
                        return 'minor'
            
            # If there are new files but no specific indicators, assume minor
            if len(added_files) > 0:
                print(f"Minor update detected due to new files: {len(added_files)} new files")
                return 'minor'
        
        # Default to patch for modifications
        if modified_files:
            print(f"Patch update detected due to modified files: {len(modified_files)} files")
            return 'patch'
        
        # If no changes detected, default to patch
        print("No significant changes detected, defaulting to patch")
        return 'patch'
    
    def get_current_version(self) -> version.Version:
        """
        Get current version from version.json or last release tag.
        
        Returns:
            Current Version object
        """
        # Try to get from version.json first
        version_file = self.repo_root / "version.json"
        if version_file.exists():
            try:
                with open(version_file, 'r') as f:
                    data = json.load(f)
                    return version.Version(data['version'])
            except Exception:
                pass
        
        # Fall back to last release tag
        last_tag = self.get_last_release_tag()
        if last_tag:
            return version.Version(last_tag)
        
        # Default to 1.0.0
        return version.Version("1.0.0")


class GitHubReleaser:
    """Handles GitHub release creation and file uploads."""
    
    def __init__(self, repo_owner: str, repo_name: str, token: Optional[str] = None):
        """
        Initialize GitHub releaser.
        
        Args:
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
            token: GitHub personal access token (optional)
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.token = token
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    
    def create_release(self, tag: str, version_obj: version.Version,
                      manifest_data: Dict[str, Any], files_to_upload: List[str]) -> bool:
        """
        Create a new GitHub release with manifest and files.
        
        Args:
            tag: Release tag (e.g., "v1.2.3")
            version_obj: Version object
            manifest_data: Manifest content
            files_to_upload: List of files to include in release
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate inputs
            if not tag or not version_obj or not manifest_data:
                print("Error: Missing required parameters for release creation")
                return False
            
            # Check if tag already exists
            if self._tag_exists(tag):
                print(f"Error: Tag {tag} already exists")
                return False
            
            # Prepare release data
            release_data = {
                "tag_name": tag,
                "target_commitish": "main",  # Could be configurable
                "name": f"Release {tag}",
                "body": self._generate_release_notes(version_obj, manifest_data),
                "draft": False,
                "prerelease": False
            }
            
            # Create release
            release_json = json.dumps(release_data)
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Python-Release-Script"
            }
            
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            
            # Create release request with timeout
            req = urllib.request.Request(
                f"{self.api_base}/releases",
                data=release_json.encode('utf-8'),
                headers=headers
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status == 201:
                    release_info = json.loads(response.read().decode('utf-8'))
                    release_id = release_info.get('id')
                    if release_id:
                        print(f"Created release {tag} (ID: {release_id})")
                    else:
                        print("Error: No release ID in response")
                        return False
                elif response.status == 422:
                    print(f"Error: Release already exists or validation failed (status {response.status})")
                    return False
                else:
                    error_data = response.read().decode('utf-8')
                    print(f"Failed to create release: {response.status}")
                    try:
                        error_json = json.loads(error_data)
                        print(f"GitHub API error: {error_json.get('message', 'Unknown error')}")
                    except:
                        print(f"Response: {error_data}")
                    return False
            
            # Upload manifest.json first
            if not self._upload_release_asset(release_info, "manifest.json",
                                            json.dumps(manifest_data, indent=2)):
                print("Failed to upload manifest.json")
                return False
            
            # Upload other files with error tracking
            upload_success = 0
            for file_path in files_to_upload:
                if os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    if self._upload_release_asset(release_info, filename, file_path):
                        upload_success += 1
                else:
                    print(f"Warning: File not found for upload: {file_path}")
            
            print(f"Uploaded {upload_success}/{len(files_to_upload)} files successfully")
            
            if upload_success == len(files_to_upload):
                print(f"Successfully uploaded release {tag}")
                return True
            else:
                print("Some files failed to upload")
                return False
            
        except urllib.error.HTTPError as e:
            print(f"HTTP Error creating release: {e.code} - {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"Network Error creating release: {e.reason}")
            return False
        except Exception as e:
            print(f"Unexpected error creating release: {e}")
            return False
    
    def _tag_exists(self, tag: str) -> bool:
        """
        Check if a tag already exists in the repository.
        
        Args:
            tag: Tag to check
            
        Returns:
            True if tag exists, False otherwise
        """
        try:
            with urllib.request.urlopen(f"{self.api_base}/git/refs/tags/{tag}", timeout=10) as response:
                return response.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            print(f"Error checking tag existence: {e}")
            return True  # Assume it exists to be safe
        except Exception as e:
            print(f"Error checking tag existence: {e}")
            return True  # Assume it exists to be safe
    
    def _upload_release_asset(self, release_info: Dict[str, Any], 
                             filename: str, content_or_path: str) -> bool:
        """
        Upload an asset to a release.
        
        Args:
            release_info: Release information from GitHub API
            filename: Name of the file
            content_or_path: File content or path to file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            upload_url = release_info['upload_url'].replace('{?name,label}', '')
            
            # Determine if content_or_path is file content or file path
            if os.path.exists(content_or_path):
                with open(content_or_path, 'rb') as f:
                    content = f.read()
            else:
                content = content_or_path.encode('utf-8')
            
            headers = {
                "Content-Type": "application/octet-stream",
                "User-Agent": "Python-Release-Script"
            }
            
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            
            req = urllib.request.Request(
                f"{upload_url}?name={filename}",
                data=content,
                headers=headers
            )
            
            with urllib.request.urlopen(req) as response:
                if response.status == 201:
                    print(f"Uploaded asset: {filename}")
                    return True
                else:
                    print(f"Failed to upload {filename}: {response.status}")
                    return False
                    
        except Exception as e:
            print(f"Error uploading asset {filename}: {e}")
            return False
    
    def _generate_release_notes(self, version_obj: version.Version, 
                               manifest_data: Dict[str, Any]) -> str:
        """
        Generate release notes based on manifest data.
        
        Args:
            version_obj: Version object
            manifest_data: Manifest data
            
        Returns:
            Release notes string
        """
        notes = f"## Release {version_obj}\n\n"
        
        files_add = manifest_data.get('files_add', [])
        files_edit = manifest_data.get('files_edit', [])
        files_delete = manifest_data.get('files_delete', [])
        
        if files_add:
            notes += "### Added\n"
            for file in files_add:
                notes += f"- {file}\n"
            notes += "\n"
        
        if files_edit:
            notes += "### Modified\n"
            for file in files_edit:
                notes += f"- {file}\n"
            notes += "\n"
        
        if files_delete:
            notes += "### Removed\n"
            for file in files_delete:
                notes += f"- {file}\n"
            notes += "\n"
        
        if 'req.txt' in manifest_data:
            notes += "### Dependencies\n"
            notes += "- Updated requirements\n"
            notes += "\n"
        
        return notes


class ReleaseManager:
    """Manages the complete release process."""
    
    def __init__(self, repo_root: str = "."):
        """
        Initialize release manager.
        
        Args:
            repo_root: Root directory of the repository
        """
        self.repo_root = Path(repo_root)
        self.analyzer = ChangeAnalyzer(repo_root)
    
    def create_manifest(self, version_obj: version.Version, 
                       added_files: Set[str], modified_files: Set[str], 
                       deleted_files: Set[str]) -> Dict[str, Any]:
        """
        Create manifest.json content.
        
        Args:
            version_obj: Version object
            added_files: Set of added files
            modified_files: Set of modified files
            deleted_files: Set of deleted files
            
        Returns:
            Manifest data dictionary
        """
        manifest = {
            "version": str(version_obj),
            "files_add": list(added_files),
            "files_edit": list(modified_files),
            "files_delete": list(deleted_files),
            "build_date": "2025-11-19"  # Could be dynamic
        }
        
        # Include requirements.txt if it exists or was changed
        req_file = self.repo_root / "requirements.txt"
        if req_file.exists() or "requirements.txt" in modified_files:
            manifest["req.txt"] = True
        
        return manifest
    
    def prepare_release_files(self, manifest: Dict[str, Any]) -> List[str]:
        """
        Prepare list of files to upload with the release.
        
        Args:
            manifest: Manifest data
            
        Returns:
            List of file paths to upload
        """
        files_to_upload = []
        
        # Add all files that are being added or edited
        for filename in manifest.get('files_add', []) + manifest.get('files_edit', []):
            file_path = self.repo_root / filename
            if file_path.exists():
                files_to_upload.append(str(file_path))
        
        # Always include requirements.txt if specified
        if 'req.txt' in manifest:
            req_file = self.repo_root / "requirements.txt"
            if req_file.exists():
                files_to_upload.append(str(req_file))
        
        return files_to_upload
    
    def create_release(self, repo_owner: str, repo_name: str, 
                      target_version: Optional[str] = None) -> bool:
        """
        Create a new release.
        
        Args:
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
            target_version: Target version (auto-determined if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Analyze changes
            added_files, modified_files, deleted_files = self.analyzer.get_changed_files_since_last_release()
            
            if not (added_files or modified_files or deleted_files):
                print("No changes detected since last release")
                return True
            
            # Determine version bump
            bump_type = self.analyzer.determine_version_bump(added_files, modified_files, deleted_files)
            
            # Calculate new version
            current_version = self.analyzer.get_current_version()
            if target_version:
                new_version = version.Version(target_version)
            else:
                if bump_type == 'major':
                    new_version = current_version.bump_major()
                elif bump_type == 'minor':
                    new_version = current_version.bump_minor()
                else:
                    new_version = current_version.bump_patch()
            
            print(f"Creating release: {current_version} → {new_version} ({bump_type})")
            
            # Create manifest
            manifest = self.create_manifest(new_version, added_files, modified_files, deleted_files)
            
            # Prepare files for upload
            files_to_upload = self.prepare_release_files(manifest)
            
            # Save manifest locally
            with open(self.repo_root / "manifest.json", 'w') as f:
                json.dump(manifest, f, indent=2)
            
            print(f"Manifest created: {len(manifest.get('files_add', []))} added, "
                  f"{len(manifest.get('files_edit', []))} modified, "
                  f"{len(manifest.get('files_delete', []))} deleted")
            
            # Update version.json
            version_data = {
                "version": str(new_version),
                "build_date": "2025-11-19",
                "description": f"Release {new_version}"
            }
            
            with open(self.repo_root / "version.json", 'w') as f:
                json.dump(version_data, f, indent=2)
            
            # Create GitHub release
            token = os.getenv('GITHUB_TOKEN')  # Get from environment
            releaser = GitHubReleaser(repo_owner, repo_name, token)
            tag = f"v{new_version}"
            
            success = releaser.create_release(tag, new_version, manifest, files_to_upload)
            
            if success:
                print(f"Release {tag} created successfully!")
                
                # Commit and push changes
                try:
                    subprocess.run(["git", "add", "version.json", "manifest.json"], 
                                 cwd=self.repo_root, check=True)
                    subprocess.run(["git", "commit", "-m", f"Release {tag}"], 
                                 cwd=self.repo_root, check=True)
                    subprocess.run(["git", "tag", tag], cwd=self.repo_root, check=True)
                    subprocess.run(["git", "push", "origin", "main", "--tags"], 
                                 cwd=self.repo_root, check=True)
                    print("Changes committed and pushed to repository")
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Could not commit changes: {e}")
            
            return success
            
        except Exception as e:
            print(f"Error creating release: {e}")
            return False


def main():
    """Main entry point for the release script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create a new release")
    parser.add_argument("--version", help="Target version (e.g., 1.2.3)")
    parser.add_argument("--repo", default="owner/repo", 
                       help="GitHub repository in format owner/repo")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be done without actually creating release")
    
    args = parser.parse_args()
    
    # Parse repository
    if "/" not in args.repo:
        print("Repository must be in format owner/repo")
        sys.exit(1)
    
    owner, repo = args.repo.split("/", 1)
    
    if args.dry_run:
        print("DRY RUN MODE - No actual changes will be made")
    
    # Create release
    release_manager = ReleaseManager()
    if args.dry_run:
        # Show what would happen
        print("\n=== DRY RUN ANALYSIS ===")
        
        # Analyze changes
        added_files, modified_files, deleted_files = release_manager.analyzer.get_changed_files_since_last_release()
        
        if not (added_files or modified_files or deleted_files):
            print("No changes detected since last release")
            return
        
        print(f"Files to add: {len(added_files)}")
        for file in sorted(added_files):
            print(f"  + {file}")
        
        print(f"Files to modify: {len(modified_files)}")
        for file in sorted(modified_files):
            print(f"  ~ {file}")
        
        print(f"Files to delete: {len(deleted_files)}")
        for file in sorted(deleted_files):
            print(f"  - {file}")
        
        # Determine version bump
        bump_type = release_manager.analyzer.determine_version_bump(added_files, modified_files, deleted_files)
        current_version = release_manager.analyzer.get_current_version()
        
        if bump_type == 'major':
            new_version = current_version.bump_major()
        elif bump_type == 'minor':
            new_version = current_version.bump_minor()
        else:
            new_version = current_version.bump_patch()
        
        print(f"\nVersion bump: {bump_type}")
        print(f"Current version: {current_version}")
        print(f"New version: {new_version}")
        print(f"Target release tag: v{new_version}")
        
        # Create manifest preview
        manifest = release_manager.create_manifest(new_version, added_files, modified_files, deleted_files)
        print(f"\nManifest preview:")
        print(json.dumps(manifest, indent=2))
        
        print("\n=== END DRY RUN ===")
        return
    
    success = release_manager.create_release(owner, repo, args.version)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

    