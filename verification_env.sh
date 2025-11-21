#!/bin/bash

set +e  # Continue on errors

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Arrays to track issues
declare -a ISSUES_FOUND
declare -a ISSUES_FIXED
declare -a CRITICAL_ERRORS

# Helper functions
print_status() {
    local message="$1"
    local type="${2:-Info}"
    
    case "$type" in
        "Success")
            echo -e "${GREEN}[✓]${NC} $message"
            ;;
        "Error")
            echo -e "${RED}[✗]${NC} $message"
            ;;
        "Warning")
            echo -e "${YELLOW}[!]${NC} $message"
            ;;
        "Info")
            echo -e "${CYAN}[i]${NC} $message"
            ;;
        *)
            echo "[-] $message"
            ;;
    esac
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "osx"
    else
        echo "unknown"
    fi
}

# Detect architecture
detect_arch() {
    local arch=$(uname -m)
    case "$arch" in
        x86_64|amd64)
            echo "x86_64"
            ;;
        arm64|aarch64)
            echo "arm64"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Test internet connection
test_internet() {
    print_status "Checking internet connectivity..." "Info"
    
    if curl -s --connect-timeout 5 https://www.google.com > /dev/null 2>&1; then
        print_status "Internet connection: OK" "Success"
        return 0
    else
        print_status "Internet connection: FAILED" "Warning"
        ISSUES_FOUND+=("No internet connection")
        return 1
    fi
}

# Test if port is in use
test_port() {
    local port=$1
    local service_name=$2
    
    if command -v nc &> /dev/null; then
        if nc -z localhost "$port" 2>/dev/null; then
            print_status "$service_name (port $port): Already running" "Success"
        else
            print_status "$service_name (port $port): Not running (will start with initiate.py)" "Info"
        fi
    elif command -v lsof &> /dev/null; then
        if lsof -i:"$port" &> /dev/null; then
            print_status "$service_name (port $port): Already running" "Success"
        else
            print_status "$service_name (port $port): Not running (will start with initiate.py)" "Info"
        fi
    else
        print_status "$service_name (port $port): Cannot check (nc/lsof not available)" "Info"
    fi
    
    return 0
}

# Test micromamba installation
test_micromamba() {
    print_status "Checking micromamba installation..." "Info"
    
    local micromamba_path="$HOME/.codemate/micromamba"
    
    if [[ -f "$micromamba_path" ]] && [[ -x "$micromamba_path" ]]; then
        print_status "Micromamba: Found" "Success"
        return 0
    else
        print_status "Micromamba: NOT FOUND" "Error"
        ISSUES_FOUND+=("Micromamba not installed")
        
        print_status "Downloading micromamba..." "Info"
        
        mkdir -p "$HOME/.codemate"
        
        local os_type=$(detect_os)
        local arch=$(detect_arch)
        local url=""
        
        if [[ "$os_type" == "linux" ]]; then
            if [[ "$arch" == "arm64" ]]; then
                url="https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0/micromamba-linux-aarch64"
            else
                url="https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0/micromamba-linux-64"
            fi
        elif [[ "$os_type" == "osx" ]]; then
            if [[ "$arch" == "arm64" ]]; then
                url="https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0/micromamba-osx-arm64"
            else
                url="https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0/micromamba-osx-64"
            fi
        else
            print_status "Unsupported OS: $os_type" "Error"
            CRITICAL_ERRORS+=("Unsupported operating system")
            return 1
        fi
        
        if curl -L "$url" -o "$micromamba_path" --connect-timeout 30; then
            chmod +x "$micromamba_path"
            print_status "Micromamba downloaded successfully" "Success"
            ISSUES_FIXED+=("Downloaded micromamba")
            return 0
        else
            print_status "Failed to download micromamba" "Error"
            CRITICAL_ERRORS+=("Micromamba download failed")
            return 1
        fi
    fi
}

# Create Python environment
create_python_environment() {
    local micromamba_path="$HOME/.codemate/micromamba"
    local env_path="$HOME/.codemate/environment"
    
    if [[ ! -x "$micromamba_path" ]]; then
        print_status "Cannot create environment: micromamba not found" "Error"
        CRITICAL_ERRORS+=("Micromamba not available for environment creation")
        return 1
    fi
    
    # Remove corrupted environment if it exists
    if [[ -d "$env_path" ]]; then
        rm -rf "$env_path"
    fi
    
    print_status "Creating Python 3.11 environment..." "Info"
    
    if "$micromamba_path" create --prefix "$env_path" python=3.11 -y; then
        if [[ -f "$env_path/bin/python" ]]; then
            print_status "Python environment created successfully" "Success"
            ISSUES_FIXED+=("Created Python environment")
            return 0
        else
            print_status "Failed to create Python environment" "Error"
            CRITICAL_ERRORS+=("Python environment creation failed")
            return 1
        fi
    else
        print_status "Error creating Python environment" "Error"
        CRITICAL_ERRORS+=("Python environment creation error")
        return 1
    fi
}

# Test Python environment
test_python_environment() {
    print_status "Checking Python environment..." "Info"
    
    local python_path="$HOME/.codemate/environment/bin/python"
    
    if [[ -f "$python_path" ]]; then
        # Test if Python actually works
        if version=$("$python_path" --version 2>&1); then
            print_status "Python environment: Found ($version)" "Success"
            return 0
        else
            print_status "Python environment: Corrupted" "Error"
            ISSUES_FOUND+=("Python environment corrupted")
            
            print_status "Recreating Python environment..." "Info"
            create_python_environment
            return $?
        fi
    else
        print_status "Python environment: NOT FOUND" "Error"
        ISSUES_FOUND+=("Python environment not created")
        
        print_status "Creating Python environment..." "Info"
        create_python_environment
        return $?
    fi
}

# Test Python packages
test_python_packages() {
    print_status "Checking Python packages..." "Info"
    
    local python_path="$HOME/.codemate/environment/bin/python"
    
    if [[ ! -f "$python_path" ]]; then
        print_status "Cannot check packages: Python not found" "Error"
        return 1
    fi
    
    # Use the same requirements.txt location that install_env.sh uses
    local requirements_path="$HOME/.codemate/requirements.txt"
    
    # Key packages that initiate.py needs
    local critical_packages=(
        "fastapi"
        "uvicorn"
        "requests"
        "pydantic"
        "loguru"
        "python-socketio"
        "aiohttp"
        "psutil"
        "qdrant-client"
        "tinydb"
    )
    
    print_status "Verifying critical packages..." "Info"
    local missing_packages=()
    
    for package in "${critical_packages[@]}"; do
        local import_name="${package//-/_}"
        if "$python_path" -c "import $import_name" 2>/dev/null; then
            print_status "  $package: OK" "Success"
        else
            print_status "  $package: MISSING" "Error"
            missing_packages+=("$package")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        ISSUES_FOUND+=("Missing packages: ${missing_packages[*]}")
        print_status "Found ${#missing_packages[@]} missing critical packages" "Warning"
        
        if [[ -f "$requirements_path" ]]; then
            print_status "Installing all packages from requirements.txt (same as install_env.sh)..." "Info"
            
            if "$python_path" -m pip install --upgrade pip && \
               "$python_path" -m pip install -r "$requirements_path"; then
                print_status "Packages installed successfully" "Success"
                ISSUES_FIXED+=("Installed missing Python packages")
                
                # Verify installation
                local still_missing=()
                for package in "${missing_packages[@]}"; do
                    local import_name="${package//-/_}"
                    if ! "$python_path" -c "import $import_name" 2>/dev/null; then
                        still_missing+=("$package")
                    fi
                done
                
                if [[ ${#still_missing[@]} -gt 0 ]]; then
                    print_status "Still missing packages: ${still_missing[*]}" "Error"
                    CRITICAL_ERRORS+=("Failed to install: ${still_missing[*]}")
                    return 1
                fi
                
                return 0
            else
                print_status "Failed to install packages" "Error"
                CRITICAL_ERRORS+=("Package installation failed")
                return 1
            fi
        else
            print_status "Requirements file not found at $requirements_path" "Error"
            print_status "Please run install_env.sh first to create the requirements file" "Error"
            CRITICAL_ERRORS+=("Requirements file not found - run install_env.sh first")
            return 1
        fi
    else
        print_status "All critical packages: OK" "Success"
        return 0
    fi
}

# Test required files
test_required_files() {
    print_status "Checking required files..." "Info"
    
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local required_files=(
        "$script_dir/initiate.py"
        "$script_dir/http_server.py"
        "$script_dir/websocket_server.py"
        "$script_dir/ipc.py"
    )
    
    local all_files_exist=true
    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_status "  $(basename "$file"): Found" "Success"
        else
            print_status "  $(basename "$file"): NOT FOUND" "Error"
            CRITICAL_ERRORS+=("Required file missing: $(basename "$file")")
            all_files_exist=false
        fi
    done
    
    [[ "$all_files_exist" == true ]]
    return $?
}

# Test Qdrant binary
test_qdrant_binary() {
    print_status "Checking Qdrant binary..." "Info"
    
    # Qdrant will be downloaded by initiate.py if not present
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local possible_paths=(
        "$HOME/.codemate/qdrant"
        "$script_dir/qdrant"
        "$script_dir/BASE/vdb/qdrant"
    )
    
    local found=false
    for path in "${possible_paths[@]}"; do
        if [[ -f "$path" ]]; then
            print_status "Qdrant binary: Found at $path" "Success"
            found=true
            break
        fi
    done
    
    if [[ "$found" == false ]]; then
        print_status "Qdrant binary: Not found (will be downloaded by initiate.py)" "Info"
    fi
    
    return 0  # Not critical since initiate.py handles this
}

# Test system requirements
test_system_requirements() {
    print_status "Checking system requirements..." "Info"
    
    # Check available disk space
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local free_space_gb=$(df -BG "$script_dir" | awk 'NR==2 {print $4}' | sed 's/G//')
    
    if [[ "$free_space_gb" -lt 5 ]]; then
        print_status "Disk space: LOW (${free_space_gb}GB free)" "Warning"
        ISSUES_FOUND+=("Low disk space: ${free_space_gb}GB")
    else
        print_status "Disk space: OK (${free_space_gb}GB free)" "Success"
    fi
    
    # Check available memory
    if command -v free &> /dev/null; then
        local free_ram_gb=$(free -g | awk 'NR==2 {print $7}')
        if [[ "$free_ram_gb" -lt 2 ]]; then
            print_status "Available RAM: LOW (${free_ram_gb}GB free)" "Warning"
            ISSUES_FOUND+=("Low available RAM")
        else
            print_status "Available RAM: OK (${free_ram_gb}GB free)" "Success"
        fi
    else
        print_status "Cannot check RAM (free command not available)" "Info"
    fi
    
    return 0
}

# Show summary
show_summary() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}         VERIFICATION SUMMARY${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    
    if [[ ${#ISSUES_FIXED[@]} -gt 0 ]]; then
        echo -e "${GREEN}Issues Fixed (${#ISSUES_FIXED[@]}):${NC}"
        for fix in "${ISSUES_FIXED[@]}"; do
            echo -e "${GREEN}  ✓ $fix${NC}"
        done
        echo ""
    fi
    
    if [[ ${#ISSUES_FOUND[@]} -gt 0 ]]; then
        echo -e "${YELLOW}Issues Found (${#ISSUES_FOUND[@]}):${NC}"
        for issue in "${ISSUES_FOUND[@]}"; do
            echo -e "${YELLOW}  ! $issue${NC}"
        done
        echo ""
    fi
    
    if [[ ${#CRITICAL_ERRORS[@]} -gt 0 ]]; then
        echo -e "${RED}Critical Errors (${#CRITICAL_ERRORS[@]}):${NC}"
        for error in "${CRITICAL_ERRORS[@]}"; do
            echo -e "${RED}  ✗ $error${NC}"
        done
        echo ""
        echo -e "${RED}RESULT: VERIFICATION FAILED${NC}"
        echo -e "${RED}Please run install_env.sh again or fix the errors above.${NC}"
        echo ""
        return 1
    else
        echo -e "${GREEN}RESULT: ALL CHECKS PASSED ✓${NC}"
        echo ""
        echo -e "${GREEN}Your environment is ready to run initiate.py!${NC}"
        echo ""
        echo -e "${CYAN}Next steps:${NC}"
        echo -e "${NC}  1. Run: python initiate.py${NC}"
        echo -e "${NC}  2. Or use the correct Python: ~/.codemate/environment/bin/python initiate.py${NC}"
        echo ""
        return 0
    fi
}

# Main execution
main() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  CodeMate Environment Verification${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    
    # Run all checks
    test_internet
    test_micromamba
    test_python_environment
    test_python_packages
    test_required_files
    test_qdrant_binary
    test_system_requirements
    
    # Check required ports
    print_status "Checking required ports..." "Info"
    test_port 45223 "HTTP Server"
    test_port 45224 "WebSocket Server"
    test_port 45225 "Qdrant"
    test_port 11434 "Ollama"
    
    # Show summary
    show_summary
    return $?
}

# Run main function
main
exit $?
