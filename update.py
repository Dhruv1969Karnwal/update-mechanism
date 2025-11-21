#!/usr/bin/env python3
"""
Enhanced user-side update script with improved staging system.
Handles version detection, validation, sequential updates, and file operations.
Integrates with @updater-middleware for GitHub interactions.
Enhanced to work with branch-based releases instead of tags.
Uses only standard Python libraries.

Key Improvements:
- Fresh install staging: downloads to .codemate.test.staging → .codemate.test
- Update backup staging: creates backup_staging using exclude patterns
- Exclude array for permanent files/folders
- Cross-platform compatibility with pathlib
- Enhanced cleanup mechanisms
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
import platform
import version
try:
    import setup_tracker
except ImportError:
    # Fallback when setup_tracker is not available (backward compatibility)
    setup_tracker = None

# Define exclude patterns for permanent files/folders
EXCLUDE_PATTERNS = [
    # User data and permanent folders
    'user_data/',
    'config/user_settings.json', 
    'logs/',
    'cache/',
    'temp/',
    'backup_*/',  # Backup directories
    'staging*/',  # Staging directories
    
    # Temporary files
    '*.tmp',
    '*.temp',
    '*.bak',
    
    # Environment and sensitive files
    '.env',
    '.env.*',
    '*.key',
    '*.secret',
    
    # User-generated content
    'user_files/',
    'documents/',
    'media/',
    
    # System files that should not be overwritten
    '.DS_Store',
    'Thumbs.db',
    'desktop.ini'
]


class MiddlewareUpdater:
    """Handles interactions with the updater middleware for GitHub operations."""
    
    def __init__(self, middleware_url: str = "http://localhost:8000", repo: str = None):
        """
        Initialize middleware updater.
        
        Args:
            middleware_url: Base URL of the middleware server
            repo: Repository in format owner/repo (overrides middleware default)
        """
        self.middleware_url = middleware_url.rstrip('/')
        self.repo = repo
        self.timeout = 30

    def _make_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make a request to the middleware.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            JSON response data
            
        Raises:
            Exception: If request fails
        """
        try:
            url = f"{self.middleware_url}{endpoint}"
            if self.repo:
                separator = '&' if '?' in endpoint else '?'
                url += f"{separator}repo={self.repo}"
            
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
                else:
                    raise Exception(f"HTTP {response.status}: {response.read().decode('utf-8')}")
                    
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Exception("Resource not found")
            elif e.code == 429:
                raise Exception("Rate limit exceeded. Please try again later.")
            else:
                raise Exception(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    def get_release_manifest(self, version_tag: str) -> Optional[Dict[str, Any]]:
        """
        Fetch manifest.json for a specific release from middleware.
        
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
            
            endpoint = f"/manifest/{tag}"
            print(f"ENDPOINT SEND TO /manifest/version", endpoint)
            return self._make_request(endpoint)
            
        except Exception as e:
            print(f"Error fetching manifest: {e}")
            return None

    def download_file(self, version_tag: str, filename: str, target_path: str) -> bool:
        """
        Download a file from a specific release via middleware.
        
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
            
            # Construct download URL
            download_url = f"{self.middleware_url}/download/{tag}/{filename}"
            if self.repo:
                download_url += f"?repo={self.repo}"
            
            # Create directory if it doesn't exist
            target_path_obj = Path(target_path)
            target_dir = target_path_obj.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Download with timeout
            with urllib.request.urlopen(download_url, timeout=self.timeout) as response:
                if response.status == 200:
                    content = response.read()
                    
                    # Verify content is not empty
                    if not content:
                        print(f"Error: Downloaded file {filename} is empty")
                        return False
                    
                    # Write file directly (backup staging handles backup at directory level)
                    with open(target_path_obj, 'wb') as f:
                        f.write(content)
                    
                    # Verify file was written correctly
                    if target_path_obj.exists() and target_path_obj.stat().st_size > 0:
                        print(f"Successfully downloaded: {filename}")
                        return True
                    else:
                        print(f"Error: Failed to write file: {target_path}")
                        return False
                else:
                    print(f"HTTP Error {response.status} downloading {filename}")
                    return False
                    
        except Exception as e:
            print(f"Error downloading {filename}: {e}")
            return False

    def list_releases(self) -> List[str]:
        """
        List all available releases from middleware.
        
        Returns:
            List of release dictionaries
        """
        try:
            data = self._make_request("/releases")
            return data
        except Exception as e:
            print(f"Error listing releases: {e}")
            return []


    def get_codebase_info(self, version_tag: str) -> Optional[Dict[str, Any]]:
        """
        Get codebase information for a release.
        
        Args:
            version_tag: Version tag
            
        Returns:
            Codebase information or None if not found
        """
        try:
            tag = version_tag.lstrip('vV')
            if not tag.startswith('v'):
                tag = f'v{tag}'
            
            return self._make_request(f"/codebase/{tag}")
        except Exception as e:
            print(f"Error getting codebase info: {e}")
            return None


def _get_exclude_function(exclude_patterns: List[str] = None) -> callable:
    """
    Create ignore function for shutil.copytree that handles exclude patterns.
    
    Args:
        exclude_patterns: List of patterns to exclude
        
    Returns:
        Function for shutil.ignore_patterns
    """
    if exclude_patterns is None:
        exclude_patterns = EXCLUDE_PATTERNS
    
    # Convert to list of ignore patterns for shutil.ignore_patterns
    return shutil.ignore_patterns(*exclude_patterns)


def _safe_path(path: Path) -> Path:
    """
    Ensure path is within safe bounds (prevent path traversal).
    
    Args:
        path: Path to validate
        
    Returns:
        Safe path or raises ValueError
        
    Raises:
        ValueError: If path contains path traversal attempts
    """
    if '..' in str(path) or str(path).startswith('/') or '\\' in str(path):
        raise ValueError(f"Unsafe path: {path}")
    
    # Normalize path to resolve any . or .. components
    return path.resolve().relative_to(path.resolve().anchor)


class UpdateManager:
    """Manages the update process from start to finish with enhanced features."""
    
    def __init__(self, middleware_updater: MiddlewareUpdater, codemate_path: Optional[str] = None):
        """
        Initialize update manager.
        
        Args:
            middleware_updater: MiddlewareUpdater instance
            codemate_path: Optional path to the codemate directory (overrides default ~/.codemate.test)
        """
        self.middleware = middleware_updater
        
        # Establish the single source directory
        if codemate_path:
            self.codemate_dir = Path(codemate_path)
        else:
            self.codemate_dir = Path.home() / ".codemate.test"
            
        self.version_file = self.codemate_dir / "version.txt"
        
        # Ensure .codemate directory exists
        self.codemate_dir.mkdir(parents=True, exist_ok=True)

    def load_current_version(self) -> Optional[version.Version]:
        """
        Load current version from .codemate.test/version.txt.
        
        Returns:
            Current Version object or None if not found
        """
        try:
            if not self.version_file.exists():
                print(f"Version file not found: {self.version_file}")
                print("This appears to be a new installation.")
                return None
            
            with open(self.version_file, 'r') as f:
                version_str = f.read().strip()
                return version.Version(version_str)
                
        except Exception as e:
            print(f"Error loading current version: {e}")
            return None

    def save_version(self, ver: version.Version) -> bool:
        """
        Save version to .codemate.test/version.txt.
        
        Args:
            ver: Version to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.version_file, 'w') as f:
                f.write(str(ver))
            
            print(f"Version saved to {self.version_file}: {ver}")
            return True
            
        except Exception as e:
            print(f"Error saving version: {e}")
            return False

    def is_fresh_installation(self) -> bool:
        """
        Check if this is a fresh installation.
        
        Returns:
            True if no version file exists (fresh install)
        """
        return not self.version_file.exists()

    def perform_initial_installation(self, target_version: str) -> bool:
        """
        Perform initial installation for fresh installations using staging.
        
        Args:
        try:
            # Initialize progress tracking for codebase update
            if setup_tracker:
                setup_tracker.update_phase_progress("codebase_update", "Initializing codebase update process", True, 5)
            
            print("=" * 60)
            print("FRESH INSTALLATION FLOW")
            print("=" * 60)
            target_version: Target version to install
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print("=" * 60)
            print("FRESH INSTALLATION FLOW")
            print("=" * 60)
            
            target_ver = version.Version(target_version)
            
            # Initialize progress tracking for codebase retrieval
            if setup_tracker:
                setup_tracker.update_phase_progress("codebase_update", "Retrieving system information from remote server", True, 10)
            # Get codebase information
            print(f"Getting codebase information for version {target_ver}...")
            codebase_info = self.middleware.get_codebase_info(str(target_ver))
            
            print(f"CODEBASE INFO FROM URL /codebase/version-no. {json.dumps(codebase_info, indent=2)}")

            if not codebase_info:
                if setup_tracker:
                    setup_tracker.mark_phase_failed("codebase_update", "Failed to retrieve system information")
                print(f"Could not get codebase info for version {target_ver}")
            if not codebase_info:
                print(f"Could not get codebase info for version {target_ver}")
                return False
            
            # Get manifest for installation
            if setup_tracker:
                setup_tracker.update_phase_progress("codebase_update", "Fetching installation manifest", True, 15)
            print(f"Getting manifest for version {target_ver}...")
            # Get manifest for installation
            print(f"Getting manifest for version {target_ver}...")
            manifest = self.middleware.get_release_manifest(str(target_ver))
            if not manifest:
                if setup_tracker:
                    setup_tracker.mark_phase_failed("codebase_update", "Installation manifest not found")
                print(f"Could not find manifest for version {target_ver}")
            if not manifest:
                print(f"Could not find manifest for version {target_ver}")
                return False
            
            print(f"Installing version {target_ver}...")
            print(f"Platform: {platform.system()}")
            print(f"Architecture: {platform.machine()}")
            print(f"Installation Directory: {self.codemate_dir}")
            
            # Create staging directory for fresh install
            staging_dir = self.codemate_dir.parent / f"{self.codemate_dir.name}.staging"
            staging_dir.mkdir(parents=True, exist_ok=True)
            print(f"[STAGING] Created staging directory: {staging_dir}")
            
            try:
                # Apply manifest changes to staging directory
                if setup_tracker:
                    setup_tracker.update_phase_progress("codebase_update", "Setting up installation environment", True, 20)
                staged_manager = UpdateManager(self.middleware, str(staging_dir))
                # Apply manifest changes to staging directory
                staged_manager = UpdateManager(self.middleware, str(staging_dir))
                if not staged_manager.apply_manifest_changes(manifest, str(target_ver), is_installation=True):
                    print("[ERROR] Failed to download files to staging")
                    return False
                
                print("[STAGING] All downloads completed successfully")
                
                # Move staging to final destination
                print("[COMMIT] Moving staged files to final destination...")
                if sys.version_info >= (3, 8):
                    shutil.copytree(staging_dir, self.codemate_dir, dirs_exist_ok=True)
                else:
                    # Manual copy for older Python versions
                    if self.codemate_dir.exists():
                        shutil.rmtree(self.codemate_dir)
                    shutil.move(str(staging_dir), str(self.codemate_dir))
                
                print(f"[OK] Files moved successfully to {self.codemate_dir}")
                
                # Save version
                if not self.save_version(target_ver):
                    print("Failed to save version")
                    return False
                
                print(f"\n[OK] Fresh installation completed successfully!")
                print(f"Version {target_ver} has been installed.")
                print(f"Version file: {self.version_file}")
                
                return True
                
            except Exception as e:
                print(f"[ERROR] Error during staging: {e}")
                return False
                
            finally:
                # Always clean up staging directory
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)
                    print(f"[CLEANUP] Staging directory removed: {staging_dir}")
            
        except Exception as e:
            print(f"Error during installation: {e}")
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
            print(f"[INFO] Major update available: {current} → {target}")
            print("[WARNING]  Major updates may include breaking changes.")
            response = input("Do you want to proceed with this major update? (y/N): ").strip().lower()
            return response in ['y', 'yes']
        else:
            print(f"[PACKAGE] {update_type.capitalize()} update available: {current} → {target}")
            response = input("Do you want to proceed with this update? (y/N): ").strip().lower()
            return response in ['y', 'yes']

    def _create_safe_backup_staging(self, staging_dir: Path, version_tag: str) -> bool:
        """
        Create backup staging directory excluding permanent files.
        
        Args:
            staging_dir: Backup staging directory
            version_tag: Version for backup directory naming
            
        Returns:
            True if successful, False otherwise
        """
        try:
            backup_staging_dir = staging_dir / f"backup_staging_{version_tag}"
            backup_staging_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[BACKUP] Creating safe backup in: {backup_staging_dir}")
            
            # Copy only codebase files, excluding permanent/user files
            if self.codemate_dir.exists():
                exclude_func = _get_exclude_function()
                shutil.copytree(
                    self.codemate_dir,
                    backup_staging_dir / "original",
                    ignore=exclude_func
                )
                
                print(f"[BACKUP] Safe backup created with exclude patterns")
                print(f"         Excluded: {EXCLUDE_PATTERNS}")
                
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to create backup staging: {e}")
            return False

    def apply_manifest_changes(self, manifest: Dict[str, Any], version_tag: str, is_installation: bool = False) -> bool:
        """
        Apply changes described in manifest with enhanced error handling and staging.
        
        Args:
            manifest: Manifest data
            version_tag: Version tag for downloads
            is_installation: True if this is a fresh installation
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate manifest structure
            if not manifest or not isinstance(manifest, dict):
                print("Error: Invalid manifest format")
                return False
            
            # Support both old and new manifest formats
            manifest_version = manifest.get('version', manifest.get('manifest_version', '1.0'))
            
            operation_type = "installation" if is_installation else "update"
            print(f"\n[LIST] Applying manifest changes for {operation_type}...")
            print(f"[FILE] Manifest version: {manifest_version}")
            
            # Handle enhanced manifest structure (new format)
            if 'codebase' in manifest:
                codebase = manifest['codebase']
                files_add = codebase.get('files_add', [])
                files_edit = codebase.get('files_edit', [])
                files_delete = codebase.get('files_delete', [])
                
                print(f"[DIR] Codebase directory: {codebase.get('directory', 'N/A')}")
                print(f"[TOOLS] Total files to process: {len(files_add) + len(files_edit) + len(files_delete)}")
            else:
                # Legacy manifest format
                files_add = manifest.get('files_add', [])
                files_edit = manifest.get('files_edit', [])
                files_delete = manifest.get('files_delete', [])
            
            success_count = 0
            total_operations = 0
            failed_operations = []
            
            # Phase 1: Delete files
            if files_delete:
                print(f"\n[DELETE]  Deleting {len(files_delete)} file(s)...")
                total_operations += len(files_delete)
                for filename in files_delete:
                    if not self._validate_filename(filename):
                        error_msg = f"Invalid filename for deletion: {filename}"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
                        continue
                    
                    file_path = self.codemate_dir / filename
                    if file_path.exists():
                        try:
                            print(f"   [DELETE]  {filename}")
                            if file_path.is_dir():
                                shutil.rmtree(file_path)
                            else:
                                file_path.unlink()
                            success_count += 1
                        except Exception as e:
                            error_msg = f"Failed to delete {filename}: {e}"
                            print(f"[ERROR] {error_msg}")
                            failed_operations.append(error_msg)
                    else:
                        print(f"   [SKIP]  {filename} (not found)")
                        success_count += 1  # Not an error
            
            # Phase 2: Add/Download files
            if files_add:
                print(f"\n[ADD] Adding {len(files_add)} file(s)...")
                total_operations += len(files_add)
                for filename in files_add:
                    if not self._validate_filename(filename):
                        error_msg = f"Invalid filename for addition: {filename}"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
                        continue
                    
                    target_path = self.codemate_dir / filename
                    print(f"   [DOWNLOAD]  {filename}")
                    if self.middleware.download_file(version_tag, filename, str(target_path)):
                        success_count += 1
                    else:
                        error_msg = f"Failed to download {filename}"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
            
            # Phase 3: Edit/Replace files
            if files_edit:
                print(f"\n[EDIT]  Updating {len(files_edit)} file(s)...")
                total_operations += len(files_edit)
                for filename in files_edit:
                    if not self._validate_filename(filename):
                        error_msg = f"Invalid filename for editing: {filename}"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
                        continue
                    
                    target_path = self.codemate_dir / filename
                    print(f"   [UPDATE] {filename}")
                    if self.middleware.download_file(version_tag, filename, str(target_path)):
                        success_count += 1
                    else:
                        error_msg = f"Failed to download {filename}"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
            
            # Phase 4: Handle dependencies
            if 'req.txt' in manifest or manifest.get('dependencies'):
                total_operations += 1
                print(f"\n[PACKAGE] Installing dependencies...")
                
                # Download requirements.txt if not already present
                req_path = self.codemate_dir / "requirements.txt"
                if self.middleware.download_file(version_tag, "requirements.txt", str(req_path)):
                    try:
                        print("   [PACKAGE] Installing Python dependencies...")
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=300  # 5 minute timeout
                        )
                        print("   [OK] Dependencies installed successfully")
                        success_count += 1
                    except subprocess.TimeoutExpired:
                        error_msg = "Dependencies installation timed out after 5 minutes"
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Failed to install dependencies: {e}"
                        print(f"[ERROR] {error_msg}")
                        if e.stderr:
                            print(f"   Pip error: {e.stderr.strip()}")
                        failed_operations.append(error_msg)
                    except FileNotFoundError:
                        error_msg = "Pip not found. Please ensure pip is installed."
                        print(f"[ERROR] {error_msg}")
                        failed_operations.append(error_msg)
                else:
                    error_msg = "Failed to download requirements.txt"
                    print(f"[ERROR] {error_msg}")
                    failed_operations.append(error_msg)
            
            # Report results
            print(f"\n[STATUS] Operations completed: {success_count}/{total_operations}")
            
            if failed_operations:
                print(f"[ERROR] Failed operations ({len(failed_operations)}):")
                for error in failed_operations:
                    print(f"   • {error}")
            
            if success_count == total_operations:
                print(f"[OK] All {operation_type} operations completed successfully")
                return True
            else:
                print(f"[WARNING]  Some operations failed. Check logs above.")
                if not is_installation:
                    self._rollback_changes(manifest_version)
                return False
            
        except Exception as e:
            print(f"[CRITICAL] Critical error applying manifest changes: {e}")
            if not is_installation:
                self._rollback_changes(manifest.get('version', 'unknown'))
            return False

    def _rollback_changes(self, backup_version: str) -> None:
        """
        Rollback changes using backup.
        
        Args:
            backup_version: Version identifier for backup
        """
        try:
            backup_dir = self.codemate_dir / f"backup_{backup_version}"
            if backup_dir.exists():
                print(f"[UPDATE] Rolling back changes using backup...")
                
                # Restore from backup
                # NOTE: Since backup_dir is inside codemate_dir, we cannot delete codemate_dir entirely
                # We use copytree with dirs_exist_ok=True to restore files
                if sys.version_info >= (3, 8):
                    shutil.copytree(backup_dir, self.codemate_dir, dirs_exist_ok=True)
                else:
                    # Fallback for older python versions if necessary, though Python 3 is expected
                    # Remove contents of codemate_dir excluding backups/staging to ensure clean state
                    for item in self.codemate_dir.iterdir():
                        if item.name.startswith('backup_') or item.name.startswith('staging'):
                            continue
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    
                    # Copy files back
                    for item in backup_dir.iterdir():
                        dest = self.codemate_dir / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                
                print(f"[OK] Rollback completed successfully")
                print(f"[DIR] Backup location: {backup_dir}")
            else:
                print(f"[WARNING]  No backup found for rollback: {backup_dir}")
        except Exception as e:
            print(f"[ERROR] Rollback failed: {e}")

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
        suspicious_patterns = ['..', '~', '$env', '%', 'script', 'exec']
        for pattern in suspicious_patterns:
            if pattern in filename.lower():
                return False
        
        return True

    def update_to_version(self, target_version: str) -> bool:
        """
        Update application to target version with sequential updates and rollback.
        
        Args:
            target_version: Target version string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            target_ver = version.Version(target_version)
            current_ver = self.load_current_version()
            
            if not current_ver:
                return self.perform_initial_installation(target_version)
            
            print("=" * 60)
            print("UPDATE FLOW")
            print("=" * 60)
            print(f"Current version: {current_ver}")
            print(f"Target version: {target_ver}")
            
            if not self.validate_update_permissions(current_ver, target_ver):
                print("[ERROR] Update not permitted or cancelled by user")
                return False
            
            # Get intermediate versions for sequential update
            intermediate_versions = version.find_intermediate_versions(current_ver, target_ver)
            
            if not intermediate_versions:
                print(f"[TARGET] Direct update to {target_ver}")
                intermediate_versions = [target_ver]
            else:
                print(f"[UPDATE] Sequential update through: {' → '.join(map(str, intermediate_versions))}")
            
            # Create backup staging directory for updates
            backup_staging_dir = self.codemate_dir.parent / "backup_staging"
            backup_staging_dir.mkdir(parents=True, exist_ok=True)
            print(f"[BACKUP_STAGING] Directory: {backup_staging_dir}")

            try:
                # For updates, create safe backup staging first
                if not self._create_safe_backup_staging(backup_staging_dir, str(target_ver)):
                    print("[ERROR] Failed to create backup staging")
                    return False

                # Apply updates sequentially
                for i, version_to_apply in enumerate(intermediate_versions):
                    print(f"\n{'='*40}")
                    print(f"STEP {i+1}/{len(intermediate_versions)}: {version_to_apply}")
                    print(f"{'='*40}")

                    # Get manifest for this version
                    manifest = self.middleware.get_release_manifest(str(version_to_apply))
                    if not manifest:
                        print(f"[ERROR] Could not find manifest for version {version_to_apply}")
                        return False

                    # Apply changes to main codemate directory
                    if not self.apply_manifest_changes(manifest, str(version_to_apply), is_installation=False):
                        print(f"[ERROR] Failed to apply update to version {version_to_apply}")
                        return False

                    print(f"[OK] Successfully updated to version {version_to_apply}")

                    # Update version file after successful step
                    if not self.save_version(version_to_apply):
                        print(f"[ERROR] Failed to save version {version_to_apply}")
                        return False

                # Cleanup backup staging directory after successful update
                if backup_staging_dir.exists():
                    shutil.rmtree(backup_staging_dir)
                    print(f"[CLEANUP] Backup staging directory removed: {backup_staging_dir}")

                print(f"\n🎉 Update completed successfully!")
                print(f"[PACKAGE] Current version: {target_ver}")
                print(f"[FILE] Version file: {self.version_file}")

                return True

            except Exception as e:
                print(f"[CRITICAL] Error during update: {e}")
                # Leave backup staging directory for potential manual recovery
                print(f"[WARNING] Backup staging directory preserved for recovery: {backup_staging_dir}")
                return False
            
        except Exception as e:
            print(f"[CRITICAL] Error during update: {e}")
            return False


def main():
    """Main entry point for the update script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update application to a new version")
    parser.add_argument("version", nargs="?", help="Target version (e.g., 1.2.3)")
    parser.add_argument("--middleware-url", default="http://localhost:8000",
                    help="URL of the middleware server")
    parser.add_argument("--repo", 
                    help="GitHub repository in format owner/repo (overrides middleware default)")
    parser.add_argument("--list", action="store_true", 
                    help="List available versions")
    parser.add_argument("--check", action="store_true",
                    help="Check current version and available updates")

    args = parser.parse_args()

    # Initialize middleware updater
    middleware_updater = MiddlewareUpdater(args.middleware_url, args.repo)
    # UpdateManager now defaults to ~/.codemate.test
    update_manager = UpdateManager(middleware_updater)

    # Check middleware health
    try:
        health = middleware_updater._make_request("/health")
        print(f"[OK] Middleware server healthy: {health.get('status')}")
        if not health.get('github_configured'):
            print("[WARNING] GitHub authentication not configured on middleware")
    except Exception as e:
        print(f"[ERROR] Cannot connect to middleware server at {args.middleware_url}")
        print(f"Error: {e}")
        print("Please ensure the middleware server is running:")
        print("  cd updater-middleware && python main.py")
        sys.exit(1)

    # Check current status if requested
    if args.check:
        current_ver = update_manager.load_current_version()

        if current_ver:
            print(f"[PACKAGE] Current version: {current_ver}")

            try:
                versions = middleware_updater.list_releases()

                if versions:
                    print(f"[LIST] Available versions: {len(versions)} releases")
                    latest = versions[0]

                    # Normalize version string
                    latest_version = latest.get('version') or latest.lstrip('v')

                    if version.Version(latest_version) > current_ver:
                        print(f"[NEW] Update available: {latest.get('branch_name', latest_version)}")
                    else:
                        print("[OK] You are on the latest version")

                else:
                    print("[ERROR] No versions found")

            except Exception as e:
                print(f"[ERROR] Error checking versions: {e}")

            return

        else:
            print("[NEW] Not installed (fresh installation)")
            print("Run: python update.py <version> to install")
            return

    # List versions if requested
    if args.list:
        versions = middleware_updater.list_releases()
        if versions:
            print("[LIST] Available branch-based versions:")
            for version_info in versions:
                branch_name = version_info.get('branch_name', 'unknown')
                version_num = version_info.get('version', 'unknown')
                print(f"  {branch_name} (v{version_num})")
        else:
            print("[ERROR] No branch-based versions found")
        return

    # Get target version
    target_version = args.version
    if not target_version:
        if update_manager.is_fresh_installation():
            print("[NEW] Fresh installation detected.")
        target_version = input("Enter version to install (e.g., 1.2.3): ").strip()

    if not version.validate_version_string(target_version):
        print(f"[ERROR] Invalid version format: {target_version}")
        sys.exit(1)

    # Perform update or installation
    if update_manager.is_fresh_installation():
        success = update_manager.perform_initial_installation(target_version)
    else:
        success = update_manager.update_to_version(target_version)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
