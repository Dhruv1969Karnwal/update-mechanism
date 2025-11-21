#!/usr/bin/env python3
"""
Setup Orchestrator - Coordinates the complete setup process with real-time progress tracking.
Manages the flow between codebase updates and environment verification.
"""

import os
import sys
import subprocess
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Import setup tracker for progress coordination
try:
    import setup_tracker
except ImportError:
    print("Warning: setup_tracker not available. Running in standalone mode.")
    setup_tracker = None


class SetupOrchestrator:
    """Coordinates the complete setup process."""
    
    def __init__(self, version: str):
        """
        Initialize the setup orchestrator.
        
        Args:
            version: Target version for the setup (e.g., "3.0.0")
        """
        self.version = version
        self.setup_successful = False
        self.overall_exit_code = 0
        
        # Initialize progress tracking - only set status during actual initialization
        if setup_tracker:
            print(f"Setup Orchestrator initialized for version {version}")
    
    def initialize_setup_state(self) -> bool:
        """
        Initialize the setup state for frontend monitoring.
        Preserves any previously completed phases to avoid status reset.
        
        Returns:
            True if initialization successful
        """
        try:
            if setup_tracker:
                tracker = setup_tracker.get_tracker()
                current_state = tracker.load_setup_state()
                
                # Check if we have valid existing state
                overall_status = current_state.get("overall_status")
                
                if overall_status in ["completed", "failed"]:
                    # Preserve completed/failed state - don't change anything
                    print(f"Preserving final state: {overall_status} ({current_state.get('overall_progress', 0)}%)")
                    return True
                elif overall_status == "running":
                    # Resume running state
                    print(f"Resuming setup: {current_state.get('overall_progress', 0)}%")
                    return True
                else:
                    # Fresh start - set to running
                    print("Starting fresh setup")
                    tracker.update_overall_status("running", "Initializing setup process")
                    
                    # Initialize phases only if they're not already in progress
                    phases = current_state.get("phases", {})
                    if phases.get("codebase_update", {}).get("status") == "pending":
                        tracker.update_phase_progress("codebase_update", "Preparing for codebase update", True, 0)
                    if phases.get("environment_verification", {}).get("status") == "pending":
                        tracker.update_phase_progress("environment_verification", "Preparing for environment verification", True, 0)
            
            print("[OK] Setup state initialized successfully")
            return True
            
        except Exception as e:
            if setup_tracker:
                tracker.update_overall_status("error", f"Failed to initialize setup state: {e}")
            print(f"[FAIL] Failed to initialize setup state: {e}")
            return False



    def run_codebase_update(self) -> bool:
        """
        Run the codebase update process.
        
        Returns:
            True if update successful
        """
        try:
            if setup_tracker:
                setup_tracker.update_phase_progress("codebase_update", "Starting codebase update process", True, 5)
            
            print("\n" + "="*60)
            print("PHASE 1: CODEBASE UPDATE")
            print("="*60)
            
            # Run update.py with the version argument
            cmd = [sys.executable, "update.py", self.version]
            
            print(f"Executing: {' '.join(cmd)}")
            
            # Execute the update process
            result = subprocess.run(
                cmd,
                capture_output=False,  # Let output flow through for user visibility
                text=True,
                cwd=Path.cwd()
            )
            
            if result.returncode == 0:
                print("✓ Codebase update completed successfully")
                if setup_tracker:
                    setup_tracker.update_phase_progress("codebase_update", "Codebase update completed successfully", True, 100)
                return True
            else:
                print(f"[FAIL] Codebase update failed with exit code {result.returncode}")
                if setup_tracker:
                    setup_tracker.mark_phase_failed("codebase_update", f"Update process failed with exit code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"[FAIL] Exception during codebase update: {e}")
            if setup_tracker:
                setup_tracker.mark_phase_failed("codebase_update", f"Update exception: {e}")
            return False
    
    def run_environment_verification(self) -> bool:
        """
        Run the environment verification process.
        
        Returns:
            True if verification successful
        """
        try:
            if setup_tracker:
                setup_tracker.update_phase_progress("environment_verification", "Starting environment verification", True, 10)
            
            print("\n" + "="*60)
            print("PHASE 2: ENVIRONMENT VERIFICATION")
            print("="*60)
            
            # Run verification_env.py
            cmd = [sys.executable, "verification_env.py"]
            
            print(f"Executing: {' '.join(cmd)}")
            
            # Execute the verification process
            result = subprocess.run(
                cmd,
                capture_output=False,  # Let output flow through for user visibility
                text=True,
                cwd=Path.cwd()
            )
            
            if result.returncode == 0:
                print("✓ Environment verification completed successfully")
                if setup_tracker:
                    setup_tracker.update_phase_progress("environment_verification", "Environment verification completed successfully", True, 100)
                return True
            else:
                print(f"[FAIL] Environment verification failed with exit code {result.returncode}")
                if setup_tracker:
                    setup_tracker.mark_phase_failed("environment_verification", f"Verification process failed with exit code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"[FAIL] Exception during environment verification: {e}")
            if setup_tracker:
                setup_tracker.mark_phase_failed("environment_verification", f"Verification exception: {e}")
            return False
    
    def finalize_setup(self, update_success: bool, verification_success: bool) -> None:
        """
        Finalize the setup process and update overall status.
        
        Args:
            update_success: Whether the update phase succeeded
            verification_success: Whether the verification phase succeeded
        """
        if update_success and verification_success:
            self.setup_successful = True
            self.overall_exit_code = 0
            
            if setup_tracker:
                setup_tracker.update_overall_status("completed", "Setup completed successfully")
            
            print("\n" + "="*60)
            print("🎉 SETUP COMPLETED SUCCESSFULLY!")
            print("="*60)
            print(f"Version {self.version} has been installed and verified.")
            print("Your environment is ready to use.")
            
        elif not update_success:
            self.setup_successful = False
            self.overall_exit_code = 1
            
            if setup_tracker:
                setup_tracker.update_overall_status("failed", "Setup failed during codebase update phase")
            
            print("\n" + "="*60)
            print("❌ SETUP FAILED")
            print("="*60)
            print("The setup process failed during the codebase update phase.")
            print("Please check the error messages above and try again.")
            
        elif not verification_success:
            self.setup_successful = False
            self.overall_exit_code = 2
            
            if setup_tracker:
                setup_tracker.update_overall_status("failed", "Setup failed during environment verification phase")
            
            print("\n" + "="*60)
            print("⚠️  SETUP PARTIALLY COMPLETED")
            print("="*60)
            print("The codebase update succeeded, but environment verification failed.")
            print("Your application may not function correctly.")
            print("Please resolve the verification issues and try again.")
    
    def run_complete_setup(self) -> int:
        """
        Run the complete setup process orchestrating both phases.
        
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        try:
            print("🚀 Starting Setup Orchestration Process")
            print(f"Target Version: {self.version}")
            
            # Step 1: Initialize setup state
            if not self.initialize_setup_state():
                return 1
            
            # Step 2: Run codebase update
            update_success = self.run_codebase_update()
            
            # Step 3: Run environment verification
            verification_success = self.run_environment_verification()
            
            # Step 4: Finalize and report results
            self.finalize_setup(update_success, verification_success)
            
            return self.overall_exit_code
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Setup process interrupted by user")
            if setup_tracker:
                setup_tracker.update_overall_status("failed", "Setup interrupted by user")
            return 130  # Standard exit code for SIGINT
            
        except Exception as e:
            print(f"\n\n💥 Unexpected error during setup orchestration: {e}")
            if setup_tracker:
                setup_tracker.update_overall_status("error", f"Unexpected orchestration error: {e}")
            return 99  # Custom exit code for unexpected errors


def main():
    """Main entry point for the setup orchestrator."""
    parser = argparse.ArgumentParser(
        description="Orchestrate complete setup process with version installation and verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup_orchestrator.py 3.0.0
  python setup_orchestrator.py --version 2.1.5
  python setup_orchestrator.py 1.0.0 --middleware-url http://localhost:8000

This script will:
1. Initialize real-time setup state tracking
2. Run update.py to install/update the specified version
3. Run verification_env.py to verify the environment
4. Provide real-time progress updates for frontend monitoring
        """
    )
    
    parser.add_argument(
        "version",
        nargs="?",
        help="Target version to install (e.g., 3.0.0, 1.2.3)"
    )
    parser.add_argument(
        "--middleware-url",
        default="http://localhost:8000",
        help="URL of the middleware server (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    # Validate version argument
    if not args.version:
        print("Error: Version argument is required")
        print("Usage: python setup_orchestrator.py <version>")
        sys.exit(1)
    
    # Basic version format validation
    if not all(part.isdigit() for part in args.version.split('.')):
        print(f"Error: Invalid version format '{args.version}'. Expected format: major.minor.patch")
        sys.exit(1)
    
    # Set environment variable for middleware URL (for subprocess calls)
    os.environ['UPDATER_SERVER_HOST'] = args.middleware_url.split('://')[1].split(':')[0] if '://' in args.middleware_url else args.middleware_url.split(':')[0]
    os.environ['UPDATER_SERVER_PORT'] = args.middleware_url.split(':')[-1] if ':' in args.middleware_url else '8000'
    
    # Create and run the orchestrator
    orchestrator = SetupOrchestrator(args.version)
    exit_code = orchestrator.run_complete_setup()
    
    # Exit with the appropriate code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()