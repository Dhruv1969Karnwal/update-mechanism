"""
Version utility module for parsing and comparing semantic versions.
Supports major.minor.patch format with proper comparison logic.
"""

import re
from typing import Tuple, List


class Version:
    """Represents a semantic version with comparison capabilities."""
    
    def __init__(self, version_string: str):
        """
        Initialize a Version object from a version string.
        
        Args:
            version_string: Version in format "major.minor.patch"
            
        Raises:
            ValueError: If version string is invalid
        """
        self.version_string = version_string.strip()
        self.major, self.minor, self.patch = self._parse_version(version_string)
    
    def _parse_version(self, version_string: str) -> Tuple[int, int, int]:
        """
        Parse version string into major, minor, patch components.
        
        Args:
            version_string: Version string to parse
            
        Returns:
            Tuple of (major, minor, patch) as integers
            
        Raises:
            ValueError: If version format is invalid
        """
        # Remove 'v' prefix if present (e.g., v1.0.0)
        version_string = version_string.strip().lstrip('vV')
        
        # Match semantic version pattern
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_string)
        if not match:
            raise ValueError(f"Invalid version format: {version_string}. Expected format: major.minor.patch")
        
        major, minor, patch = map(int, match.groups())
        return major, minor, patch
    
    def __str__(self) -> str:
        """Return version string representation."""
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __repr__(self) -> str:
        """Return detailed version representation."""
        return f"Version('{self.version_string}')"
    
    def __eq__(self, other) -> bool:
        """Check if two versions are equal."""
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other) -> bool:
        """Check if this version is less than another."""
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other) -> bool:
        """Check if this version is less than or equal to another."""
        return self < other or self == other
    
    def __gt__(self, other) -> bool:
        """Check if this version is greater than another."""
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)
    
    def __ge__(self, other) -> bool:
        """Check if this version is greater than or equal to another."""
        return self > other or self == other
    
    def is_major_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a major update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major version is higher
        """
        return self.major > other.major
    
    def is_minor_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a minor update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major is same but minor is higher
        """
        return self.major == other.major and self.minor > other.minor
    
    def is_patch_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a patch update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major and minor are same but patch is higher
        """
        return (self.major == other.major and 
                self.minor == other.minor and 
                self.patch > other.patch)
    
    def bump_major(self) -> 'Version':
        """Return a new version with bumped major number (minor and patch reset to 0)."""
        return Version(f"{self.major + 1}.0.0")
    
    def bump_minor(self) -> 'Version':
        """Return a new version with bumped minor number (patch reset to 0)."""
        return Version(f"{self.major}.{self.minor + 1}.0")
    
    def bump_patch(self) -> 'Version':
        """Return a new version with bumped patch number."""
        return Version(f"{self.major}.{self.minor}.{self.patch + 1}")
    
    def get_update_type(self, other: 'Version') -> str:
        """
        Get the type of update from another version to this one.
        
        Args:
            other: The previous version
            
        Returns:
            'major', 'minor', 'patch', or 'same'
        """
        if self == other:
            return 'same'
        elif self.is_major_update(other):
            return 'major'
        elif self.is_minor_update(other):
            return 'minor'
        elif self.is_patch_update(other):
            return 'patch'
        else:
            return 'unknown'


def find_intermediate_versions(current: Version, target: Version) -> List[Version]:
    """
    Generate a list of intermediate versions needed to update from current to target.
    
    Args:
        current: Current version
        target: Target version
        
    Returns:
        List of versions to update through sequentially
    """
    if current >= target:
        return []
    
    versions = []
    current_version = current
    
    # Step through major versions
    while current_version.major < target.major:
        next_major = current_version.bump_major()
        versions.append(next_major)
        current_version = next_major
    
    # Step through minor versions
    while current_version.minor < target.minor:
        next_minor = current_version.bump_minor()
        versions.append(next_minor)
        current_version = next_minor
    
    # Step through patch versions
    while current_version.patch < target.patch:
        next_patch = current_version.bump_patch()
        versions.append(next_patch)
        current_version = next_patch
    
    return versions


def validate_version_string(version_string: str) -> bool:
    """
    Validate if a string is a proper semantic version.
    
    Args:
        version_string: Version string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        Version(version_string)
        return True
    except ValueError:
        return False