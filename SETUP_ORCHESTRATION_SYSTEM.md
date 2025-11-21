# Setup Orchestration System Documentation

## Overview

The Setup Orchestration System provides a comprehensive solution for managing application installation and environment verification with real-time progress tracking for frontend monitoring.

## System Architecture

### Components

1. **setup_tracker.py** - Core progress tracking with atomic writes
2. **update.py** - Enhanced with progress tracking for codebase updates
3. **verification_env.py** - Enhanced with progress tracking for environment verification
4. **setup_orchestrator.py** - Main coordinator that orchestrates the entire process

## Key Features

### Real-Time Progress Tracking
- **Atomic Write Operations**: Uses temporary files + atomic rename for crash-safe state updates
- **Sequential Locking**: File-based locking ensures frontend reads don't conflict with writes
- **Production-Ready Messages**: All progress messages use high-level, abstract descriptions
- **Dynamic Progress Percentages**: Realistic progress calculation based on actual operations

### Frontend Integration
- **JSON State File**: `~/.codemate.test/setup_state.json` for real-time monitoring
- **Pollable Interface**: Frontend can poll the JSON file for live updates
- **Phase-Based Progress**: Separate tracking for "codebase_update" and "environment_verification"
- **Lock-Free Reads**: Frontend can safely read state while system writes

### Error Handling & Recovery
- **Graceful Failure Management**: Each phase can fail independently without affecting others
- **Clear Error Messages**: Production-ready error descriptions
- **Rollback Support**: Automatic rollback on update failures
- **Backward Compatibility**: All scripts work standalone without the orchestration system

## JSON State Structure

```json
{
  "setup_id": "setup_1640995200",
  "timestamp": "2023-12-31T23:00:00.123456",
  "overall_status": "running",
  "overall_progress": 45,
  "phases": {
    "codebase_update": {
      "status": "running",
      "progress": 70,
      "current_step": "Downloading application files",
      "steps_completed": [
        "Initializing installation process",
        "Retrieving system information from remote server",
        "Fetching installation manifest"
      ],
      "steps_total": 10,
      "start_time": "2023-12-31T23:00:01.000000",
      "end_time": null
    },
    "environment_verification": {
      "status": "pending",
      "progress": 0,
      "current_step": "Preparing for environment verification",
      "steps_completed": [],
      "steps_total": 8,
      "start_time": null,
      "end_time": null
    }
  },
  "error_details": null,
  "metadata": {
    "version": "1.0",
    "platform": "win32",
    "python_version": "3.11.0"
  }
}
```

## Usage

### Quick Start
```bash
# Run complete setup orchestration
python setup_orchestrator.py 3.0.0

# Run with custom middleware URL
python setup_orchestrator.py 3.0.0 --middleware-url http://custom-server:8000

# Check status via state file
cat ~/.codemate.test/setup_state.json
```

### Standalone Mode
```bash
# Run individual components (backward compatible)
python update.py 3.0.0
python verification_env.py
```

### Progress Monitoring
```bash
# Monitor progress in real-time
watch -n 1 "cat ~/.codemate.test/setup_state.json | python -m json.tool"
```

## Implementation Details

### Atomic Write Pattern
```python
def _safe_atomic_write(self, data):
    temp_fd, temp_path = tempfile.mkstemp(
        dir=self.state_file_path.parent,
        prefix=f"{self.state_file_path.stem}.tmp."
    )
    try:
        with os.fdopen(temp_fd, 'w') as temp_file:
            json.dump(data, temp_file, indent=2)
        os.replace(temp_path, self.state_file_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
```

### Sequential Locking
```python
def _acquire_lock(self, timeout=5):
    while time.time() - start_time < timeout:
        try:
            self._lock_file = open(self._lock_file_path, 'w')
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            time.sleep(0.1)
    return False
```

### Progress Updates
```python
def update_phase_progress(self, phase, step_description, 
                         step_completed=True, additional_progress=0):
    state = self.load_setup_state()
    phase_data = state["phases"][phase]
    phase_data["current_step"] = step_description
    
    if step_completed and step_description not in phase_data["steps_completed"]:
        phase_data["steps_completed"].append(step_description)
    
    current_progress = phase_data["progress"]
    max_progress = min(100, current_progress + additional_progress)
    phase_data["progress"] = max_progress
    
    return self._safe_atomic_write(state)
```

## Error Scenarios

### Network Failure
```json
{
  "overall_status": "failed",
  "error_details": "codebase_update: Failed to retrieve system information"
}
```

### Permission Denied
```json
{
  "overall_status": "failed", 
  "error_details": "environment_verification: Environment manager initialization failed"
}
```

### Partial Success
```json
{
  "overall_status": "failed",
  "error_details": "Setup failed during environment verification phase"
}
```

## Monitoring & Debugging

### Check Overall Status
```bash
cat ~/.codemate.test/setup_state.json | jq '.overall_status, .overall_progress'
```

### Monitor Specific Phase
```bash
cat ~/.codemate.test/setup_state.json | jq '.phases.codebase_update'
```

### View Step History
```bash
cat ~/.codemate.test/setup_state.json | jq '.phases.environment_verification.steps_completed'
```

## Configuration

### Environment Variables
- `UPDATER_SERVER_HOST`: Middleware server hostname
- `UPDATER_SERVER_PORT`: Middleware server port
- `HTTP_SERVER_PORT`: HTTP server port for application
- `WEBSOCKET_SERVER_PORT`: WebSocket server port
- `QDRANT_PORT`: Vector database port
- `OLLAMA_PORT`: AI model server port

### File Locations
- Setup State: `~/.codemate.test/setup_state.json`
- Lock File: `~/.codemate.test/setup_state.lock`
- Version File: `~/.codemate.test/version.txt`
- Requirements: `~/.codemate.test/requirements.txt`

## Performance Considerations

- **Lock Timeout**: 5 seconds default, configurable
- **Progress Update Frequency**: Minimal to avoid performance impact
- **JSON File Size**: Compact structure for fast reads
- **Atomic Operations**: Ensure no corruption on crashes

## Security Notes

- **Path Traversal Protection**: All file operations validated
- **Input Sanitization**: Version strings and filenames validated
- **Network Security**: HTTPS for all remote communications
- **File Permissions**: Proper permission handling for all operations

## Future Enhancements

1. **Multi-User Support**: Concurrent setup sessions
2. **Progress Persistence**: Resume interrupted setups
3. **Remote Monitoring**: WebSocket updates for live dashboards
4. **Rollback History**: Track multiple rollback versions
5. **Progress Analytics**: Detailed timing and performance metrics