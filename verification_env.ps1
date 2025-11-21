$ErrorActionPreference = "Continue"
$script:issuesFound = @()
$script:issuesFixed = @()
$script:criticalErrors = @()

function Write-Status {
    param([string]$Message, [string]$Type = "Info")
    
    $color = switch ($Type) {
        "Success" { "Green" }
        "Error" { "Red" }
        "Warning" { "Yellow" }
        "Info" { "Cyan" }
        default { "White" }
    }
    
    $prefix = switch ($Type) {
        "Success" { "[✓]" }
        "Error" { "[✗]" }
        "Warning" { "[!]" }
        "Info" { "[i]" }
        default { "[-]" }
    }
    
    Write-Host "$prefix $Message" -ForegroundColor $color
}

function Test-InternetConnection {
    Write-Status "Checking internet connectivity..." "Info"
    try {
        $response = Invoke-WebRequest -Uri "https://www.google.com" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Status "Internet connection: OK" "Success"
            return $true
        }
    } catch {
        Write-Status "Internet connection: FAILED" "Warning"
        $script:issuesFound += "No internet connection"
        return $false
    }
}

function Test-PortAvailable {
    param([int]$Port, [string]$ServiceName)
    
    try {
        $connection = Test-NetConnection -ComputerName "localhost" -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($connection) {
            Write-Status "$ServiceName (port $Port): Already running" "Success"
            return $true
        } else {
            Write-Status "$ServiceName (port $Port): Not running (will start with initiate.py)" "Info"
            return $true
        }
    } catch {
        Write-Status "$ServiceName (port $Port): Port check OK" "Success"
        return $true
    }
}

function Test-MicromambaInstallation {
    Write-Status "Checking micromamba installation..." "Info"
    
    $micromambaPath = "$env:USERPROFILE\.codemate.test\micromamba.exe"
    
    if (Test-Path $micromambaPath) {
        Write-Status "Micromamba: Found" "Success"
        return $true
    } else {
        Write-Status "Micromamba: NOT FOUND" "Error"
        $script:issuesFound += "Micromamba not installed"
        
        Write-Status "Downloading micromamba..." "Info"
        try {
            New-Item -Path "$env:USERPROFILE\.codemate.test" -ItemType Directory -Force | Out-Null
            Invoke-WebRequest -Uri "https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0/micromamba-win-64.exe" -OutFile $micromambaPath
            Write-Status "Micromamba downloaded successfully" "Success"
            $script:issuesFixed += "Downloaded micromamba"
            return $true
        } catch {
            Write-Status "Failed to download micromamba: $_" "Error"
            $script:criticalErrors += "Micromamba download failed"
            return $false
        }
    }
}

function Test-PythonEnvironment {
    Write-Status "Checking Python environment..." "Info"
    
    $pythonPath = "$env:USERPROFILE\.codemate.test\environment\python.exe"
    $envPath = "$env:USERPROFILE\.codemate.test\environment"
    
    if (Test-Path $pythonPath) {
        # Test if Python actually works
        try {
            $version = & $pythonPath --version 2>&1
            Write-Status "Python environment: Found ($version)" "Success"
            return $true
        } catch {
            Write-Status "Python environment: Corrupted" "Error"
            $script:issuesFound += "Python environment corrupted"
            
            # Try to recreate environment
            Write-Status "Recreating Python environment..." "Info"
            return New-PythonEnvironment
        }
    } else {
        Write-Status "Python environment: NOT FOUND" "Error"
        $script:issuesFound += "Python environment not created"
        
        Write-Status "Creating Python environment..." "Info"
        return New-PythonEnvironment
    }
}

function New-PythonEnvironment {
    $micromambaPath = "$env:USERPROFILE\.codemate.test\micromamba.exe"
    $envPath = "$env:USERPROFILE\.codemate.test\environment"
    
    if (-not (Test-Path $micromambaPath)) {
        Write-Status "Cannot create environment: micromamba not found" "Error"
        $script:criticalErrors += "Micromamba not available for environment creation"
        return $false
    }
    
    try {
        # Remove corrupted environment if it exists
        if (Test-Path $envPath) {
            Remove-Item -Path $envPath -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        Write-Status "Creating Python 3.11 environment..." "Info"
        & $micromambaPath create --prefix $envPath python=3.11 -y
        
        if (Test-Path "$envPath\python.exe") {
            Write-Status "Python environment created successfully" "Success"
            $script:issuesFixed += "Created Python environment"
            return $true
        } else {
            Write-Status "Failed to create Python environment" "Error"
            $script:criticalErrors += "Python environment creation failed"
            return $false
        }
    } catch {
        Write-Status "Error creating Python environment: $_" "Error"
        $script:criticalErrors += "Python environment creation error: $_"
        return $false
    }
}

function Test-PythonPackages {
    Write-Status "Checking Python packages..." "Info"
    
    $pythonPath = "$env:USERPROFILE\.codemate.test\environment\python.exe"
    
    if (-not (Test-Path $pythonPath)) {
        Write-Status "Cannot check packages: Python not found" "Error"
        return $false
    }
    
    # Use the same requirements.txt location that install_env.ps1 uses
    $requirementsPath = "$env:USERPROFILE\.codemate.test\requirements.txt"
    
    # Key packages that initiate.py absolutely needs
    $criticalPackages = @(
        "fastapi",
        "uvicorn",
        "requests",
        "pydantic",
        "loguru",
        "python-socketio",
        "aiohttp",
        "psutil",
        "qdrant-client",
        "tinydb"
    )
    
    Write-Status "Verifying critical packages..." "Info"
    $missingPackages = @()
    
    foreach ($package in $criticalPackages) {
        try {
            $result = & $pythonPath -c "import $($package.Replace('-', '_'))" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Status "  $package: OK" "Success"
            } else {
                Write-Status "  $package: MISSING" "Error"
                $missingPackages += $package
            }
        } catch {
            Write-Status "  $package: MISSING" "Error"
            $missingPackages += $package
        }
    }
    
    if ($missingPackages.Count -gt 0) {
        $script:issuesFound += "Missing packages: $($missingPackages -join ', ')"
        Write-Status "Found $($missingPackages.Count) missing critical packages" "Warning"
        
        if (Test-Path $requirementsPath) {
            Write-Status "Installing all packages from requirements.txt (same as install_env.ps1)..." "Info"
            try {
                & $pythonPath -m pip install --upgrade pip
                & $pythonPath -m pip install -r $requirementsPath
                Write-Status "Packages installed successfully" "Success"
                $script:issuesFixed += "Installed missing Python packages"
                
                # Verify installation
                $stillMissing = @()
                foreach ($package in $missingPackages) {
                    $result = & $pythonPath -c "import $($package.Replace('-', '_'))" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        $stillMissing += $package
                    }
                }
                
                if ($stillMissing.Count -gt 0) {
                    Write-Status "Still missing packages: $($stillMissing -join ', ')" "Error"
                    $script:criticalErrors += "Failed to install: $($stillMissing -join ', ')"
                    return $false
                }
                
                return $true
            } catch {
                Write-Status "Failed to install packages: $_" "Error"
                $script:criticalErrors += "Package installation failed: $_"
                return $false
            }
        } else {
            Write-Status "requirements.txt not found at $requirementsPath" "Error"
            Write-Status "Please run install_env.ps1 first to create the requirements file" "Error"
            $script:criticalErrors += "requirements.txt not found - run install_env.ps1 first"
            return $false
        }
    } else {
        Write-Status "All critical packages: OK" "Success"
        return $true
    }
}

function Test-RequiredFiles {
    Write-Status "Checking required files..." "Info"
    
    $requiredFiles = @(
        "$PSScriptRoot\initiate.py",
        "$PSScriptRoot\http_server.py",
        "$PSScriptRoot\websocket_server.py",
        "$PSScriptRoot\ipc.py"
    )
    
    $allFilesExist = $true
    foreach ($file in $requiredFiles) {
        if (Test-Path $file) {
            Write-Status "  $(Split-Path -Leaf $file): Found" "Success"
        } else {
            Write-Status "  $(Split-Path -Leaf $file): NOT FOUND" "Error"
            $script:criticalErrors += "Required file missing: $(Split-Path -Leaf $file)"
            $allFilesExist = $false
        }
    }
    
    return $allFilesExist
}

function Test-QdrantBinary {
    Write-Status "Checking Qdrant binary..." "Info"
    
    # Qdrant will be downloaded by initiate.py if not present
    # Just check if it's already there
    $possiblePaths = @(
        "$env:USERPROFILE\.codemate.test\qdrant.exe",
        "$PSScriptRoot\qdrant.exe",
        "$PSScriptRoot\BASE\vdb\qdrant.exe"
    )
    
    $found = $false
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            Write-Status "Qdrant binary: Found at $path" "Success"
            $found = $true
            break
        }
    }
    
    if (-not $found) {
        Write-Status "Qdrant binary: Not found (will be downloaded by initiate.py)" "Info"
    }
    
    return $true  # Not critical since initiate.py handles this
}

function Test-SystemRequirements {
    Write-Status "Checking system requirements..." "Info"
    
    # Check available disk space
    $drive = (Get-Item $PSScriptRoot).PSDrive.Name
    $disk = Get-PSDrive $drive
    $freeSpaceGB = [math]::Round($disk.Free / 1GB, 2)
    
    if ($freeSpaceGB -lt 5) {
        Write-Status "Disk space: LOW ($freeSpaceGB GB free)" "Warning"
        $script:issuesFound += "Low disk space: $freeSpaceGB GB"
    } else {
        Write-Status "Disk space: OK ($freeSpaceGB GB free)" "Success"
    }
    
    # Check available memory
    $totalRAM = (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize / 1MB
    $freeRAM = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    
    if ($freeRAM -lt 2) {
        Write-Status "Available RAM: LOW ($([math]::Round($freeRAM, 2)) GB free)" "Warning"
        $script:issuesFound += "Low available RAM"
    } else {
        Write-Status "Available RAM: OK ($([math]::Round($freeRAM, 2)) GB free)" "Success"
    }
    
    return $true
}

function Show-Summary {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "         VERIFICATION SUMMARY" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    if ($script:issuesFixed.Count -gt 0) {
        Write-Host "Issues Fixed ($($script:issuesFixed.Count)):" -ForegroundColor Green
        foreach ($fix in $script:issuesFixed) {
            Write-Host "  ✓ $fix" -ForegroundColor Green
        }
        Write-Host ""
    }
    
    if ($script:issuesFound.Count -gt 0) {
        Write-Host "Issues Found ($($script:issuesFound.Count)):" -ForegroundColor Yellow
        foreach ($issue in $script:issuesFound) {
            Write-Host "  ! $issue" -ForegroundColor Yellow
        }
        Write-Host ""
    }
    
    if ($script:criticalErrors.Count -gt 0) {
        Write-Host "Critical Errors ($($script:criticalErrors.Count)):" -ForegroundColor Red
        foreach ($error in $script:criticalErrors) {
            Write-Host "  ✗ $error" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "RESULT: VERIFICATION FAILED" -ForegroundColor Red
        Write-Host "Please run install_env.ps1 again or fix the errors above." -ForegroundColor Red
        Write-Host ""
        return $false
    } else {
        Write-Host "RESULT: ALL CHECKS PASSED ✓" -ForegroundColor Green
        Write-Host ""
        Write-Host "Your environment is ready to run initiate.py!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Run: python initiate.py" -ForegroundColor White
        Write-Host "  2. Or use the correct Python: $env:USERPROFILE\.codemate.test\environment\python.exe initiate.py" -ForegroundColor White
        Write-Host ""
        return $true
    }
}

# Main execution
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CodeMate Environment Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Run all checks
$internetOK = Test-InternetConnection
$micromambaOK = Test-MicromambaInstallation
$pythonOK = Test-PythonEnvironment

# Only check packages if Python is available
if ($pythonOK) {
    $packagesOK = Test-PythonPackages
} else {
    $packagesOK = $false
}

$filesOK = Test-RequiredFiles
$qdrantOK = Test-QdrantBinary
$systemOK = Test-SystemRequirements

# Check required ports
Write-Status "Checking required ports..." "Info"
Test-PortAvailable -Port 45223 -ServiceName "HTTP Server"
Test-PortAvailable -Port 45224 -ServiceName "WebSocket Server"
Test-PortAvailable -Port 45225 -ServiceName "Qdrant"
Test-PortAvailable -Port 11434 -ServiceName "Ollama"

# Show summary
$success = Show-Summary

if ($success) {
    exit 0
} else {
    exit 1
}
