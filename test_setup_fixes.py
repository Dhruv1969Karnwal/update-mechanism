#!/usr/bin/env python3
"""
Test script to verify the setup tracker fixes.
Demonstrates cumulative progress and status preservation.
"""

import sys
import os
import tempfile
import json
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, '.')

try:
    import setup_tracker
    import setup_orchestrator
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure setup_tracker.py and setup_orchestrator.py are in the current directory")
    sys.exit(1)

def test_cumulative_progress():
    """Test that overall_progress is calculated cumulatively."""
    print("\n" + "="*60)
    print("TESTING CUMULATIVE PROGRESS CALCULATION")
    print("="*60)
    
    # Create temporary state file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "test_state.json"
        
        # Create tracker instance with temp file
        tracker = setup_tracker.SetupStateTracker(str(temp_path))
        
        print("Initial state:")
        initial_state = tracker.load_setup_state()
        print(f"  Overall progress: {initial_state['overall_progress']}%")
        print(f"  Codebase status: {initial_state['phases']['codebase_update']['status']}")
        print(f"  Environment status: {initial_state['phases']['environment_verification']['status']}")
        
        # Simulate codebase update completing (50% overall progress)
        print("\nSimulating codebase update completion...")
        tracker.update_phase_progress("codebase_update", "Codebase update completed", True, 100)
        
        state_after_codebase = tracker.load_setup_state()
        print(f"  Overall progress: {state_after_codebase['overall_progress']}%")
        print(f"  Codebase status: {state_after_codebase['phases']['codebase_update']['status']}")
        print(f"  Expected: 50% (first phase completed)")
        
        # Simulate environment verification partially completing (25% of second phase)
        print("\nSimulating environment verification 50% progress...")
        tracker.update_phase_progress("environment_verification", "Halfway through verification", True, 50)
        
        state_after_env_partial = tracker.load_setup_state()
        print(f"  Overall progress: {state_after_env_partial['overall_progress']}%")
        print(f"  Environment status: {state_after_env_partial['phases']['environment_verification']['status']}")
        print(f"  Expected: 75% (50% + 25% = 75%)")
        
        # Simulate environment verification completing (25% more)
        print("\nSimulating environment verification completion...")
        tracker.update_phase_progress("environment_verification", "Environment verification completed", True, 50)
        
        final_state = tracker.load_setup_state()
        print(f"  Overall progress: {final_state['overall_progress']}%")
        print(f"  Environment status: {final_state['phases']['environment_verification']['status']}")
        print(f"  Expected: 100% (both phases completed)")
        
        # Verify calculations
        success = True
        if state_after_codebase['overall_progress'] != 50:
            print(f"[FAIL] Codebase completion should be 50%, got {state_after_codebase['overall_progress']}%")
            success = False
        if state_after_env_partial['overall_progress'] != 75:
            print(f"[FAIL] Partial environment should be 75%, got {state_after_env_partial['overall_progress']}%")
            success = False
        if final_state['overall_progress'] != 100:
            print(f"[FAIL] Final completion should be 100%, got {final_state['overall_progress']}%")
            success = False
            
        if success:
            print("[PASS] Cumulative progress calculation test PASSED")
        else:
            print("[FAIL] Cumulative progress calculation test FAILED")
            
        return success

def test_status_preservation():
    """Test that completed phases are not reset during orchestrator restart."""
    print("\n" + "="*60)
    print("TESTING STATUS PRESERVATION")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "test_state.json"
        
        # Create tracker and simulate completed codebase phase
        tracker = setup_tracker.SetupStateTracker(str(temp_path))
        
        print("Setting up scenario with completed codebase phase...")
        
        # Complete codebase phase
        tracker.update_phase_progress("codebase_update", "Codebase update completed successfully", True, 100)
        
        # Check state before orchestrator "restart"
        state_before = tracker.load_setup_state()
        print(f"Before orchestrator restart:")
        print(f"  Overall progress: {state_before['overall_progress']}%")
        print(f"  Codebase status: {state_before['phases']['codebase_update']['status']}")
        print(f"  Environment status: {state_before['phases']['environment_verification']['status']}")
        
        # Simulate orchestrator initialization (should preserve completed phases)
        print("\nSimulating orchestrator initialization...")
        
        # Create orchestrator
        orchestrator = setup_orchestrator.SetupOrchestrator("1.0.0")
        
        # Call initialize_setup_state which should preserve existing progress
        success = orchestrator.initialize_setup_state()
        
        # Check state after orchestrator initialization
        state_after_init = tracker.load_setup_state()
        print(f"After orchestrator initialization:")
        print(f"  Overall progress: {state_after_init['overall_progress']}%")
        print(f"  Overall status: {state_after_init['overall_status']}")
        print(f"  Codebase status: {state_after_init['phases']['codebase_update']['status']}")
        
        # Verify that completed phases are preserved
        if (state_after_init['phases']['codebase_update']['status'] == "completed" and
            state_after_init['overall_progress'] == 50):
            print("[PASS] Status preservation test PASSED - completed phase not reset")
            return True
        else:
            print("[FAIL] Status preservation test FAILED - phase was reset")
            return False

def main():
    """Run all tests."""
    print("Testing Setup Tracker Fixes")
    print("=" * 40)
    
    cumulative_success = test_cumulative_progress()
    preservation_success = test_status_preservation()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    if cumulative_success and preservation_success:
        print("[SUCCESS] All tests PASSED! The setup tracker fixes work correctly.")
        print("\nFixed issues:")
        print("1. [PASS] Overall progress is now cumulative (not reset)")
        print("2. [PASS] Completed phases are preserved during orchestrator restart")
        return 0
    else:
        print("[FAIL] Some tests FAILED. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())