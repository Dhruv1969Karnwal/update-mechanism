#!/usr/bin/env python3
"""
FastAPI middleware server for GitHub interactions.
Acts as an intermediary for GitHub API requests, handling authentication,
rate limiting, and caching to provide reliable access to GitHub repositories.
Enhanced to support branch-based releases instead of tags.
"""

import os
import asyncio
import logging
import subprocess
import tempfile
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Updater Middleware",
    description="GitHub API proxy for application updates",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
class Config:
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')
    GITHUB_PASSWORD = os.getenv('GITHUB_PASSWORD')
    DEFAULT_REPO = os.getenv('DEFAULT_REPO', 'Dhruv1969Karnwal/up-test-rel')
    GITHUB_API_BASE = 'https://api.github.com'
    GITHUB_DOWNLOAD_BASE = 'https://github.com'
    CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))  # 5 minutes
    RATE_LIMIT = int(os.getenv('RATE_LIMIT', '100'))  # requests per minute
    
config = Config()

# Simple in-memory cache
cache = {}
cache_timestamps = {}

# Rate limiting simple implementation
rate_limit_tracker = {}

# Pydantic models for request/response
class BranchReleaseInfo(BaseModel):
    """Enhanced model for branch-based releases."""
    branch_name: str
    version: str
    name: str
    draft: bool = False
    prerelease: bool = False
    created_at: Optional[str] = None
    commit_sha: str
    tree_url: str
    manifest_url: str
    commit_url: Optional[str] = None
    branch_url: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    github_configured: bool

class GitHubClient:
    """GitHub API client with authentication support."""
    
    def __init__(self):
        self.base_url = config.GITHUB_API_BASE
        self.download_url = config.GITHUB_DOWNLOAD_BASE
        self.headers = {"User-Agent": "Updater-Middleware/1.0"}
        
        # Setup authentication
        if config.GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {config.GITHUB_TOKEN}"
        elif config.GITHUB_USERNAME and config.GITHUB_PASSWORD:
            import base64
            credentials = base64.b64encode(
                f"{config.GITHUB_USERNAME}:{config.GITHUB_PASSWORD}".encode()
            ).decode()
            self.headers["Authorization"] = f"Basic {credentials}"
    
    async def get(self, endpoint: str) -> Dict[str, Any]:
        """Make GET request to GitHub API."""
        url = f"{self.base_url}/{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Resource not found")
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="Access forbidden - check authentication")
            else:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"GitHub API error: {response.text}"
                )
    
    async def download_file(self, url: str) -> StreamingResponse:
        """Download file from GitHub with authentication support."""
        logger.info(f"Downloading file from: {url}")
        
        # Enhanced headers for private repository access
        headers = self.headers.copy()
        if not headers.get('Authorization'):
            # For public repositories, use GitHub API rate limiting headers
            headers.update({
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Updater-Middleware/1.0'
            })
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    logger.info(f"Successfully downloaded file (size: {len(response.content)} bytes)")
                    return StreamingResponse(
                        iter([response.content]),
                        media_type="application/octet-stream"
                    )
                elif response.status_code == 404:
                    logger.error(f"File not found at URL: {url}")
                    logger.debug(f"Response headers: {dict(response.headers)}")
                    raise HTTPException(status_code=404, detail=f"File not found or not accessible: {url}")
                elif response.status_code == 403:
                    logger.error(f"Access forbidden - likely private repository or rate limit")
                    raise HTTPException(status_code=403, detail="Access forbidden - check repository permissions or authentication")
                else:
                    logger.error(f"Download failed with HTTP {response.status_code}: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Download failed: {response.text}"
                    )
            except Exception as e:
                logger.error(f"Download error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")

# Initialize GitHub client
github_client = GitHubClient()

def validate_branch_version(branch_name: str) -> Optional[str]:
    """
    Validate and extract version from branch name.
    
    Args:
        branch_name: Branch name to validate
        
    Returns:
        Version string (e.g., "1.2.3") or None if invalid
    """
    if not branch_name.startswith('release/v'):
        return None
    
    version_part = branch_name.replace('release/v', '')
    # Validate semantic version format
    parts = version_part.split('.')
    if len(parts) != 3:
        return None
    
    try:
        # Ensure all parts are valid numbers
        for part in parts:
            int(part)
        return version_part
    except ValueError:
        return None

def construct_branch_urls(version: str) -> Dict[str, str]:
    """
    Construct GitHub URLs for a given version.
    
    Args:
        version: Version string (e.g., "1.2.3", "v1.2.3", "2.0.0", "v2.0.0")
        
    Returns:
        Dictionary with tree_url and manifest_url
    """
    # Normalize version by removing 'v' prefix to avoid double prefixes
    clean_version = version.lstrip('vV')
    
    branch_name = f"release/v{clean_version}"
    repo = config.DEFAULT_REPO
    
    return {
        "tree_url": f"https://github.com/{repo}/tree/{branch_name}/release_v{clean_version}/codebase/code",
        "manifest_url": f"https://github.com/{repo}/blob/{branch_name}/release_v{clean_version}/manifest/manifest.json"
    }

def get_cache_key(endpoint: str) -> str:
    """Generate cache key for endpoint."""
    return f"cache:{endpoint}"

def is_cache_valid(key: str) -> bool:
    """Check if cache entry is still valid."""
    if key not in cache_timestamps:
        return False
    
    age = datetime.now() - cache_timestamps[key]
    return age.total_seconds() < config.CACHE_TTL

def rate_limit_check(client_ip: str):
    """Simple rate limiting check."""
    now = datetime.now()
    minute_key = f"{client_ip}:{now.strftime('%Y-%m-%d %H:%M')}"
    
    if minute_key not in rate_limit_tracker:
        rate_limit_tracker[minute_key] = 0
    
    if rate_limit_tracker[minute_key] >= config.RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    rate_limit_tracker[minute_key] += 1
    
    # Clean old entries
    old_keys = [k for k in rate_limit_tracker.keys() 
                if k.split(':')[1] < now.strftime('%Y-%m-%d %H:%M')]
    for key in old_keys:
        del rate_limit_tracker[key]

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        github_configured=bool(config.GITHUB_TOKEN or 
                            (config.GITHUB_USERNAME and config.GITHUB_PASSWORD))
    )

@app.get("/releases")
async def get_releases(repo: str = None):
    """Get list of all branch-based releases for a repository."""
    if not repo:
        repo = config.DEFAULT_REPO
    
    logger.info(f"Fetching branch-based releases for repository: {repo}")
    cache_key = get_cache_key(f"branches:{repo}")
    
    # Check cache
    if is_cache_valid(cache_key):
        logger.info(f"Returning cached releases for {repo}")
        return cache[cache_key]
    
    try:
        # Get all branches
        endpoint = f"repos/{repo}/branches"
        logger.debug(f"Fetching branches from: {endpoint}")
        
        all_branches = await github_client.get(endpoint)
        
        # Filter for release branches and create release info
        releases = []
        release_branches = []
        
        for branch in all_branches:
            branch_name = branch['name']
            version = validate_branch_version(branch_name)
            
            if version:
                release_branches.append((branch_name, version))
                logger.debug(f"Found valid release branch: {branch_name} (version: {version})")
        
        if not release_branches:
            logger.warning(f"No valid release branches found for {repo}")
            raise HTTPException(status_code=404, detail="No release branches found")
        
        # Process each release branch
        for branch_name, version in release_branches:
            try:
                # Get branch commit info
                commit_endpoint = f"repos/{repo}/branches/{branch_name}"
                branch_data = await github_client.get(commit_endpoint)
                
                urls = construct_branch_urls(version)
                
                release_info = BranchReleaseInfo(
                    branch_name=branch_name,
                    version=version,
                    name=f"Release {version}",
                    draft=False,
                    prerelease=False,
                    created_at=branch_data['commit']['commit']['author']['date'],
                    commit_sha=branch_data['commit']['sha'],
                    tree_url=urls['tree_url'],
                    manifest_url=urls['manifest_url'],
                    commit_url=branch_data['commit']['html_url'],
                    branch_url=f"https://github.com/{repo}/tree/{branch_name}"
                )
                releases.append(release_info.dict())
                
            except Exception as e:
                logger.warning(f"Failed to process branch {branch_name}: {e}")
                # Continue processing other branches instead of failing completely
        
        if not releases:
            logger.error(f"Failed to process any release branches for {repo}")
            raise HTTPException(status_code=500, detail="Failed to process release branches")
        
        # Sort by version (newest first)
        releases.sort(key=lambda x: [int(p) for p in x['version'].split('.')], reverse=True)
        
        # Cache result
        cache[cache_key] = releases
        cache_timestamps[cache_key] = datetime.now()
        
        logger.info(f"Successfully found and processed {len(releases)} release branches for {repo}")
        return releases
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error getting branch releases for {repo}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch release branches: {str(e)}")

@app.get("/manifest/{version}")
async def get_manifest(repo: str = None, version: str = None):
    """Get manifest.json for a specific branch-based release."""
    if not repo:
        repo = config.DEFAULT_REPO
    
    if not version:
        raise HTTPException(status_code=400, detail="Version parameter is required")
    
    cache_key = get_cache_key(f"manifest:{repo}:{version}")
    
    # Check cache
    if is_cache_valid(cache_key):
        return cache[cache_key]
    
    try:
        # Construct blob URL for manifest
        urls = construct_branch_urls(version)
        manifest_url = urls['manifest_url']
        
        logger.debug(f"Attempting to fetch manifest from: {manifest_url}")
        
        # Get raw content from GitHub blob
        raw_url = manifest_url.replace('https://github.com/', 'https://raw.githubusercontent.com/')
        raw_url = raw_url.replace('/blob/', '/')
        
        logger.debug(f"Using raw URL: {raw_url}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(raw_url, headers=github_client.headers)
            
            if response.status_code == 200:
                try:
                    manifest_data = response.json()
                    logger.info(f"Successfully fetched and parsed manifest JSON for version {version}")
                except Exception as json_err:
                    logger.warning(f"Manifest not valid JSON for version {version}, treating as text: {json_err}")
                    # If not JSON, treat as text
                    manifest_data = {
                        "content": response.text,
                        "content_type": "text",
                        "raw_url": raw_url
                    }
                
                # Cache result
                cache[cache_key] = manifest_data
                cache_timestamps[cache_key] = datetime.now()
                
                logger.info(f"Successfully fetched manifest for version {version} (type: {type(manifest_data).__name__})")
                return manifest_data
            else:
                logger.warning(f"Manifest not found for version {version}: HTTP {response.status_code} from {raw_url}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Manifest not found for version {version} at {raw_url}"
                )
        
    except Exception as e:
        logger.error(f"Error getting manifest for version {version}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch manifest for version {version}: {str(e)}")

@app.get("/file/{version}/{path:path}")
async def get_file_content(repo: str = None, version: str = None, path: str = None):
    """Get content of a specific file from a release."""
    if not repo:
        repo = config.DEFAULT_REPO
    
    if not version or not path:
        raise HTTPException(status_code=400, detail="Version and path are required")
    
    # Security check for path traversal
    if '..' in path or path.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    cache_key = get_cache_key(f"file:{repo}:{version}:{path}")
    
    # Check cache for small files
    if is_cache_valid(cache_key) and path.endswith(('.json', '.txt', '.py', '.md')):
        return cache[cache_key]
    
    try:
        # Try to get from release assets
        endpoint = f"repos/{repo}/releases/tags/{version.lstrip('v')}"
        release_data = await github_client.get(endpoint)
        
        asset_url = None
        for asset in release_data.get('assets', []):
            if asset['name'] == os.path.basename(path):
                asset_url = asset['url']
                break
        
        if asset_url:
            file_content = await httpx.AsyncClient().get(
                asset_url, headers=github_client.headers
            )
            if file_content.status_code == 200:
                # Cache small files
                if path.endswith(('.json', '.txt', '.py', '.md')):
                    cache[cache_key] = file_content.json() if path.endswith('.json') else file_content.text
                    cache_timestamps[cache_key] = datetime.now()
                    return cache[cache_key]
                else:
                    return StreamingResponse(
                        iter([file_content.content]),
                        media_type="application/octet-stream"
                    )
        
        raise HTTPException(status_code=404, detail="File not found")
        
    except Exception as e:
        logger.error(f"Error getting file content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{version}/{path:path}")
async def download_file(repo: str = None, version: str = None, path: str = None):
    """Download a file from a branch-based release (streaming response)."""
    if not repo:
        repo = config.DEFAULT_REPO
    
    if not version or not path:
        raise HTTPException(status_code=400, detail="Version and path are required")
    
    # Security check for path traversal
    if '..' in path or path.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    try:
        # Normalize version by removing 'v' prefix to avoid double prefixes
        clean_version = version.lstrip('vV')
        
        # Construct branch name for branch-based system
        branch_name = f"release/v{clean_version}"
        
        # First try to use GitHub API (works for private repos with auth)
        if config.GITHUB_TOKEN or (config.GITHUB_USERNAME and config.GITHUB_PASSWORD):
            try:
                # Use GitHub API to get file content
                api_url = f"{config.GITHUB_API_BASE}/repos/{repo}/contents/{path}"
                if branch_name != 'main':
                    api_url += f"?ref={branch_name}"
                
                logger.info(f"Using GitHub API to download {path} from version {version}")
                response_data = await github_client.get(f"repos/{repo}/contents/{path}?ref={branch_name}")
                
                if response_data.get('encoding') == 'base64' and 'content' in response_data:
                    import base64
                    content = base64.b64decode(response_data['content'])
                    return StreamingResponse(
                        iter([content]),
                        media_type="application/octet-stream"
                    )
                else:
                    # Fallback to raw URL if API doesn't work
                    logger.warning("API download failed, trying raw URL")
                    pass
            except Exception as api_error:
                logger.warning(f"API download failed: {api_error}")
        
        # Fallback: Construct raw content URL for public repositories
        download_url = f"https://raw.githubusercontent.com/{repo}/{branch_name}/release_v{clean_version}/codebase/code/{path}"
        
        logger.info(f"Downloading {path} from version {version} (branch: {branch_name})")
        logger.debug(f"URL: {download_url}")
        return await github_client.download_file(download_url)
        
    except Exception as e:
        logger.error(f"Error downloading file for version {version}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/codebase/{version}")
async def get_codebase_info(repo: str = None, version: str = None):
    """Get information about the codebase structure for a branch-based release."""
    if not repo:
        repo = config.DEFAULT_REPO

    if not version:
        raise HTTPException(status_code=400, detail="Version parameter is required")

    try:
        # Normalize version by removing 'v' prefix to avoid double prefixes
        clean_version = version.lstrip('vV')

        # Get manifest first
        manifest = await get_manifest(repo, version)

        # Construct branch URLs
        urls = construct_branch_urls(version)

        # Extract codebase information
        branch_name = f"release/v{clean_version}"
        codebase_info = {
            "version": manifest.get("version", clean_version),
            "branch_name": branch_name,
            "codebase": manifest.get("codebase", {}),
            "tree_url": urls['tree_url'],
            "manifest_url": urls['manifest_url'],
            "download_base_url": f"https://raw.githubusercontent.com/{repo}/{branch_name}/release_v{clean_version}/codebase",
            "commit_sha": None  # Will be populated if needed
        }

        # Try to get commit SHA for this version
        try:
            branch_endpoint = f"repos/{repo}/branches/release/{clean_version}"
            branch_data = await github_client.get(branch_endpoint)
            codebase_info["commit_sha"] = branch_data['commit']['sha']
        except:
            # Branch might not exist, continue without commit SHA
            pass

        logger.info(f"Successfully fetched codebase info for version {version}")
        return codebase_info

    except Exception as e:
        logger.error(f"Error getting codebase info for version {version}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/clone_codebase/{version}")
async def clone_codebase(repo: str = None, version: str = None):
    """Clone repository, checkout branch, and extract all files from codebase/code directory."""
    if not repo:
        repo = config.DEFAULT_REPO

    if not version:
        raise HTTPException(status_code=400, detail="Version parameter is required")

    try:
        clean_version = version.lstrip('vV')
        branch_name = f"release/v{clean_version}"

        # Construct authenticated repo URL for private repositories
        logger.info(f"GITHUB_TOKEN present: {bool(config.GITHUB_TOKEN)}")
        logger.info(f"GITHUB_USERNAME present: {bool(config.GITHUB_USERNAME)}")
        logger.info(f"GITHUB_PASSWORD present: {bool(config.GITHUB_PASSWORD)}")

        if config.GITHUB_TOKEN:
            repo_url = f"https://{config.GITHUB_TOKEN}@github.com/{repo}"
            logger.info(f"Using token-based authentication for repo: {repo}")
        elif config.GITHUB_USERNAME and config.GITHUB_PASSWORD:
            repo_url = f"https://{config.GITHUB_USERNAME}:{config.GITHUB_PASSWORD}@github.com/{repo}"
            logger.info(f"Using username/password authentication for repo: {repo}")
        else:
            repo_url = f"https://github.com/{repo}"
            logger.warning("No GitHub authentication configured - clone may fail for private repositories")
            logger.warning("Please set GITHUB_TOKEN in .env file for private repository access")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone repo
            logger.info(f"Cloning repository: {repo_url.replace(config.GITHUB_TOKEN or '', '***TOKEN***')}")
            logger.info(f"Target branch: {branch_name}")
            subprocess.run(["git", "clone", repo_url, temp_dir], check=True, capture_output=True, text=True)

            # Checkout branch
            subprocess.run(["git", "checkout", branch_name], cwd=temp_dir, check=True, capture_output=True, text=True)

            # Check README
            release_folder = Path(temp_dir) / f"release_v{clean_version}"
            readme_file = release_folder / "README.md"
            if not readme_file.exists():
                logger.warning(f"README.md not found in {release_folder}")

            # Extract all files from codebase/code
            codebase_code = release_folder / "codebase" / "code"
            if not codebase_code.exists():
                raise HTTPException(status_code=404, detail=f"Codebase code directory not found: {codebase_code}")

            files_dict = {}

            def collect_files(base_path, rel_path=""):
                for item in base_path.iterdir():
                    item_rel_path = f"{rel_path}/{item.name}" if rel_path else item.name
                    if item.is_file():
                        try:
                            with open(item, 'r', encoding='utf-8') as f:
                                content = f.read()
                            files_dict[item_rel_path] = {"content": content, "is_binary": False}
                        except UnicodeDecodeError:
                            # Binary file
                            with open(item, 'rb') as f:
                                content = f.read()
                            import base64
                            files_dict[item_rel_path] = {"content": base64.b64encode(content).decode('utf-8'), "is_binary": True}
                    elif item.is_dir():
                        collect_files(item, item_rel_path)

            collect_files(codebase_code)

            logger.info(f"Successfully cloned and extracted {len(files_dict)} files for version {version}")
            return {"files": files_dict}

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e.stderr}")
    except Exception as e:
        logger.error(f"Error cloning codebase for version {version}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug/url/{version}/{path:path}")
async def debug_url_construction(repo: str = None, version: str = None, path: str = None):
    """Debug endpoint to check how URLs are constructed for troubleshooting."""
    if not repo:
        repo = config.DEFAULT_REPO
    
    if not version or not path:
        raise HTTPException(status_code=400, detail="Version and path are required")
    
    # Normalize version
    clean_version = version.lstrip('vV')
    branch_name = f"release/v{clean_version}"
    
    # Construct URLs
    raw_url = f"https://raw.githubusercontent.com/{repo}/{branch_name}/release_v{clean_version}/codebase/code/{path}"
    blob_url = f"https://github.com/{repo}/blob/{branch_name}/release_v{clean_version}/codebase/code/{path}"
    
    # Test if file exists via API
    api_url = f"repos/{repo}/contents/{path}?ref={branch_name}"
    
    debug_info = {
        "input": {
            "version": version,
            "path": path,
            "repo": repo
        },
        "constructed": {
            "branch_name": branch_name,
            "clean_version": clean_version,
            "raw_url": raw_url,
            "blob_url": blob_url,
            "api_endpoint": api_url
        },
        "authentication": {
            "github_token_configured": bool(config.GITHUB_TOKEN),
            "github_basic_configured": bool(config.GITHUB_USERNAME and config.GITHUB_PASSWORD),
            "has_authorization_header": bool(config.GITHUB_TOKEN or (config.GITHUB_USERNAME and config.GITHUB_PASSWORD))
        },
        "recommendations": [
            "For private repositories, use GitHub API endpoint instead of raw URL",
            "For public repositories, raw.githubusercontent.com should work",
            "Ensure the file exists at the constructed path",
            "Check that the branch name is correct"
        ]
    }
    
    return debug_info

@app.get("/setup_script")
async def get_setup_script():
    """Return a short setup script for pre-setup execution."""
    return {"script": "echo 'Pre-setup script executed from middleware'"}

if __name__ == "__main__":
    import uvicorn
    
    # Check if GitHub authentication is configured
    if not config.GITHUB_TOKEN and not (config.GITHUB_USERNAME and config.GITHUB_PASSWORD):
        logger.warning("No GitHub authentication configured. Rate limits will be restricted.")
    
    logger.info(f"Starting updater middleware server for repository: {config.DEFAULT_REPO}")
    logger.info(f"GitHub authentication configured: {bool(config.GITHUB_TOKEN or config.GITHUB_PASSWORD)}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.LOG_LEVEL.lower()
    )