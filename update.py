#!/usr/bin/env python3
"""
User-side update script for applying application updates.
 Handles version detection, validation, sequential updates, and file operations.
 Uses only standard Python libraries.
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any
from pathlib import Path

import version


class GitHubUpdater:
    """Handles GitHub API interactions for fetching release information and files."""
    
    def __init__(self, repo_owner: str, repo_name: str):
        """
        Initialize GitHub updater.
        
        Args:
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.download_base = f"https://github.com/{repo_owner}/{repo_name}/releases/download"
    
    def get_release_manifest(self, version_tag: str) -> Optional[Dict[str, Any]]:
        """
        Fetch manifest.json for a specific release.
        
        Args:
            version_tag: Version tag (e.g., "v1.2.3" or "1.2.3")
            
        Returns:
            Manifest data dictionary or None if not found
        """
        try:
            # Normalize version tag
            tag = version_tag.lstrip('vV')
            if not tag.startswith('v'):
                tag = f'v{tag}'
            
            # Try to fetch manifest from release assets
            manifest_url = f"{self.download_base}/{tag}/manifest.json"
            
            with urllib.request.urlopen(manifest_url) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
            
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Release {tag} not found")
            else:
                print(f"HTTP Error fetching manifest: {e}")
        except Exception as e:
            print(f"Error fetching manifest: {e}")
        
        return None
    
    def download_file(self, version_tag: str, filename: str, target_path: str) -> bool:
        """
        Download a file from a specific release.
        
        Args:
            version_tag: Version tag
            filename: Name of file to download
            target_path: Local path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate inputs
            if not version_tag or not filename:
                print("Error: Version tag and filename cannot be empty")
                return False
            
            # Normalize version tag
            tag = version_tag.lstrip('vV')
            if not tag.startswith('v'):
                tag = f'v{tag}'
            
            # Validate filename for security
            if '..' in filename or filename.startswith('/') or '\\' in filename:
                print(f"Error: Invalid filename path: {filename}")
                return False
            
            download_url = f"{self.download_base}/{tag}/{filename}"
            
            # Create directory if it doesn't exist
            target_dir = os.path.dirname(target_path)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            
            # Download with timeout
            with urllib.request.urlopen(download_url, timeout=30) as response:
                if response.status == 200:
                    content = response.read()
                    
                    # Verify content is not empty
                    if not content:
                        print(f"Error: Downloaded file {filename} is empty")
                        return False
                    
                    # Create backup if file exists
                    if os.path.exists(target_path):
                        backup_path = f"{target_path}.backup"
                        shutil.copy2(target_path, backup_path)
                        print(f"Created backup: {backup_path}")
                    
                    # Write file
                    with open(target_path, 'wb') as f:
                        f.write(content)
                    
                    # Verify file was written correctly
                    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                        print(f"Successfully downloaded: {filename}")
                        return True
                    else:
                        print(f"Error: Failed to write file: {target_path}")
                        return False
                else:
                    print(f"HTTP Error {response.status} downloading {filename}")
                    return False
            
        except urllib.error.HTTPError as e:
            print(f"HTTP Error downloading {filename}: {e.code} - {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"Network Error downloading {filename}: {e.reason}")
            return False
        except PermissionError as e:
            print(f"Permission Error accessing {target_path}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error downloading {filename}: {e}")
            return False
    
    def list_releases(self) -> List[str]:
        """
        List all available releases.
        
        Returns:
            List of version tags
        """
        try:
            with urllib.request.urlopen(f"{self.api_base}/releases") as response:
                releases = json.loads(response.read().decode('utf-8'))
                return [release['tag_name'] for release in releases]
        except Exception as e:
            print(f"Error listing releases: {e}")
            return []


class UpdateManager:
    """Manages the update process from start to finish."""
    
    def __init__(self, github_updater: GitHubUpdater, app_root: str = "."):
        """
        Initialize update manager.
        
        Args:
            github_updater: GitHubUpdater instance
            app_root: Application root directory
        """
        self.github = github_updater
        self.app_root = Path(app_root)
        self.version_file = self.app_root / "version.json"
    
    def load_current_version(self) -> Optional[version.Version]:
        """
        Load current version from version.json.
        
        Returns:
            Current Version object or None if not found
        """
        try:
            if not self.version_file.exists():
                print(f"Version file not found: {self.version_file}")
                return None
            
            with open(self.version_file, 'r') as f:
                data = json.load(f)
                return version.Version(data['version'])
                
        except Exception as e:
            print(f"Error loading current version: {e}")
            return None
    
    def save_version(self, ver: version.Version) -> bool:
        """
        Save version to version.json.
        
        Args:
            ver: Version to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load existing data or create new
            if self.version_file.exists():
                with open(self.version_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {}
            
            data['version'] = str(ver)
            data['build_date'] = "2025-11-19"  # Could be dynamic
            
            with open(self.version_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error saving version: {e}")
            return False
    
    def validate_update_permissions(self, current: version.Version, target: version.Version) -> bool:
        """
        Validate if update from current to target is allowed and get user confirmation.
        
        Args:
            current: Current version
            target: Target version
            
        Returns:
            True if update is allowed, False otherwise
        """
        if target <= current:
            print(f"Target version {target} is not newer than current version {current}")
            return False
        
        update_type = target.get_update_type(current)
        
        if update_type == 'major':
            print(f"Major update available: {current} → {target}")
            print("Major updates typically include breaking changes.")
            return True
        else:
            print(f"{update_type.capitalize()} update available: {current} → {target}")
            response = input("Do you want to proceed with this update? (y/N): ").strip().lower()
            return response in ['y', 'yes']
    
    def apply_manifest_changes(self, manifest: Dict[str, Any], version_tag: str) -> bool:
        """
        Apply changes described in manifest.
        
        Args:
            manifest: Manifest data
            version_tag: Version tag for downloads
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate manifest structure
            if not manifest or not isinstance(manifest, dict):
                print("Error: Invalid manifest format")
                return False
            
            # Validate required fields
            required_fields = ['version']
            for field in required_fields:
                if field not in manifest:
                    print(f"Error: Manifest missing required field: {field}")
                    return False
            
            # Backup current state before making changes
            print("Creating backup of current state...")
            backup_dir = self.app_root / f"backup_{manifest['version']}"
            if not backup_dir.exists():
                shutil.copytree(self.app_root, backup_dir, ignore=shutil.ignore_patterns('backup_*'))
                print(f"Backup created: {backup_dir}")
            
            success_count = 0
            total_operations = 0
            
            # Delete files
            files_delete = manifest.get('files_delete', [])
            total_operations += len(files_delete)
            for filename in files_delete:
                # Validate filename for security
                if not self._validate_filename(filename):
                    print(f"Error: Invalid filename for deletion: {filename}")
                    continue
                
                file_path = self.app_root / filename
                if file_path.exists():
                    try:
                        print(f"Deleting: {filename}")
                        if file_path.is_dir():
                            shutil.rmtree(file_path)
                        else:
                            file_path.unlink()
                        success_count += 1
                    except PermissionError as e:
                        print(f"Permission denied deleting {filename}: {e}")
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")
                else:
                    print(f"File not found for deletion: {filename}")
                    success_count += 1  # Not an error
            
            # Add/Download files
            files_add = manifest.get('files_add', [])
            total_operations += len(files_add)
            for filename in files_add:
                if not self._validate_filename(filename):
                    print(f"Error: Invalid filename for addition: {filename}")
                    continue
                
                target_path = self.app_root / filename
                print(f"Adding: {filename}")
                if self.github.download_file(version_tag, filename, str(target_path)):
                    success_count += 1
                else:
                    print(f"Failed to download {filename}")
            
            # Edit/Replace files
            files_edit = manifest.get('files_edit', [])
            total_operations += len(files_edit)
            for filename in files_edit:
                if not self._validate_filename(filename):
                    print(f"Error: Invalid filename for editing: {filename}")
                    continue
                
                target_path = self.app_root / filename
                print(f"Updating: {filename}")
                if self.github.download_file(version_tag, filename, str(target_path)):
                    success_count += 1
                else:
                    print(f"Failed to download {filename}")
            
            # Install requirements if provided
            if 'req.txt' in manifest:
                total_operations += 1
                print("Installing requirements...")
                
                # Download requirements.txt if not already present
                req_path = self.app_root / "requirements.txt"
                if self.github.download_file(version_tag, "requirements.txt", str(req_path)):
                    try:
                        # Install Dependencies with timeout
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=300  # 5 minute timeout
                        )
                        print("Dependencies installed successfully")
                        success_count += 1
                    except subprocess.TimeoutExpired:
                        print("Installation timed out after 5 minutes")
                    except subprocess.CalledProcessError as e:
                        print(f"Failed to install dependencies: {e}")
                        print(f"Pip output: {e.stderr}")
                    except FileNotFoundError:
                        print("Pip not found. Please ensure pip is installed.")
                else:
                    print("Failed to download requirements.txt")
            
            # Report results
            print(f"Operations completed: {success_count}/{total_operations}")
            if success_count == total_operations:
                print("All operations completed successfully")
                return True
            else:
                print("Some operations failed. Check logs above.")
                return False
            
        except Exception as e:
            print(f"Critical error applying manifest changes: {e}")
            return False
    
    def _validate_filename(self, filename: str) -> bool:
        """
        Validate filename for security to prevent path traversal attacks.
        
        Args:
            filename: Filename to validate
            
        Returns:
            True if safe, False otherwise
        """
        if not filename:
            return False
        
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/') or '\\' in filename:
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = ['..', '~', '$env', '%']
        for pattern in suspicious_patterns:
            if pattern in filename.lower():
                return False
        
        return True
    
    def update_to_version(self, target_version: str) -> bool:
        """
        Update application to target version.
        
        Args:
            target_version: Target version string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            target_ver = version.Version(target_version)
            current_ver = self.load_current_version()
            
            if not current_ver:
                print("Could not determine current version")
                return False
            
            if not self.validate_update_permissions(current_ver, target_ver):
                print("Update not permitted or cancelled by user")
                return False
            
            # Get intermediate versions for sequential update
            intermediate_versions = version.find_intermediate_versions(current_ver, target_ver)
            
            if not intermediate_versions:
                print(f"No intermediate versions needed. Updating directly to {target_ver}")
                intermediate_versions = [target_ver]
            else:
                print(f"Will update through: {' → '.join(map(str, intermediate_versions))}")
            
            # Apply updates sequentially
            for version_to_apply in intermediate_versions:
                print(f"\nApplying update to version {version_to_apply}...")
                
                # Get manifest for this version
                manifest = self.github.get_release_manifest(str(version_to_apply))
                if not manifest:
                    print(f"Could not find manifest for version {version_to_apply}")
                    return False
                
                # Apply changes
                if not self.apply_manifest_changes(manifest, str(version_to_apply)):
                    print(f"Failed to apply update to version {version_to_apply}")
                    return False
                
                # Update version file
                if not self.save_version(version_to_apply):
                    print(f"Failed to save version {version_to_apply}")
                    return False
                
                print(f"Successfully updated to version {version_to_apply}")
            
            print(f"\nUpdate completed successfully! Current version: {target_ver}")
            return True
            
        except Exception as e:
            print(f"Error during update: {e}")
            return False


def main():
    """Main entry point for the update script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update application to a new version")
    parser.add_argument("version", nargs="?", help="Target version (e.g., 1.2.3)")
    parser.add_argument("--repo", default="owner/repo", 
                       help="GitHub repository in format owner/repo")
    parser.add_argument("--list", action="store_true", 
                       help="List available versions")
    
    args = parser.parse_args()
    
    # Parse repository
    if "/" not in args.repo:
        print("Repository must be in format owner/repo")
        sys.exit(1)
    
    owner, repo = args.repo.split("/", 1)
    github_updater = GitHubUpdater(owner, repo)
    update_manager = UpdateManager(github_updater)
    
    # List versions if requested
    if args.list:
        versions = github_updater.list_releases()
        if versions:
            print("Available versions:")
            for version in versions:
                print(f"  {version}")
        else:
            print("No versions found")
        return
    
    # Get target version
    target_version = args.version
    if not target_version:
        target_version = input("Enter target version (e.g., 1.2.3): ").strip()
    
    if not version.validate_version_string(target_version):
        print(f"Invalid version format: {target_version}")
        sys.exit(1)
    
    # Perform update
    success = update_manager.update_to_version(target_version)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()