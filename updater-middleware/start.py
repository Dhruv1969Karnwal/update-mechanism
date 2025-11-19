#!/usr/bin/env python3
"""
Startup script for the updater middleware server.
Handles dependency checking and server startup.
"""

import os
import sys
import subprocess
from pathlib import Path


def check_dependencies():
    """Check if required dependencies are installed."""
    print("Checking dependencies...")
    
    required_packages = [
        'fastapi',
        'uvicorn', 
        'httpx',
        'pydantic',
        'python-dotenv'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"[OK] {package}")
        except ImportError:
            print(f"[MISSING] {package}")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\nInstalling missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", 
                *[pkg for pkg in missing_packages]
            ], check=True)
            print("[OK] Dependencies installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install dependencies: {e}")
            return False
    
    return True


def check_configuration():
    """Check if configuration is properly set up."""
    print("\nChecking configuration...")
    
    env_file = Path('.env')
    if env_file.exists():
        print("[OK] .env file found")
        
        # Check for GitHub token
        with open('.env', 'r') as f:
            content = f.read()
            if 'GITHUB_TOKEN=' in content and not content.strip().endswith('GITHUB_TOKEN='):
                print("[OK] GitHub token configured")
            elif 'GITHUB_USERNAME=' in content and 'GITHUB_PASSWORD=' in content:
                print("[OK] GitHub basic auth configured")
            else:
                print("[WARNING] GitHub authentication not configured - rate limits will apply")
    else:
        print("[WARNING] No .env file found - using defaults")
    
    return True


def start_server():
    """Start the middleware server."""
    print("\nStarting middleware server...")
    
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
        return False
    
    return True


def main():
    """Main startup function."""
    print("=" * 60)
    print("@updater-middleware Startup Script")
    print("=" * 60)
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    print(f"Working directory: {script_dir}")
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check configuration
    if not check_configuration():
        sys.exit(1)
    
    # Start server
    start_server()


if __name__ == "__main__":
    main()