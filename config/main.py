#!/usr/bin/env python3
"""
Enhanced release script for creating comprehensive multi-platform releases.
Analyzes changes with advanced version detection, creates structured releases,
and deploys to target repositories with GitHub Actions integration.
Uses only standard Python libraries.
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import zipfile
import tempfile
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
import hashlib
import re
from datetime import datetime
from dotenv import load_dotenv