"""
Centralized ChromaDB client management.

This module provides a single source of truth for ChromaDB client creation
and configuration, ensuring all components use identical settings.
"""

from pathlib import Path

import chromadb
from chromadb import PersistentClient

# Single source of truth for ChromaDB settings
# Using default settings to match what intent_database.py expects
CHROMA_SETTINGS = {}  # Default settings

# Cache of clients by path to ensure singleton behavior
_clients: dict[str, PersistentClient] = {}


def get_chroma_client(chroma_path: Path | str) -> PersistentClient:
    """Get or create a ChromaDB client for the given path.
    
    This ensures all clients use identical settings and reuses
    existing instances where possible.
    
    Parameters
    ----------
    chroma_path : Path | str
        Path to the ChromaDB persistence directory.
        MUST be an explicit path - no defaults allowed!
        
    Returns
    -------
    PersistentClient
        The ChromaDB client instance for this path
        
    Raises
    ------
    ValueError
        If chroma_path is None, empty, or invalid
    """
    if not chroma_path:
        raise ValueError(
            "ChromaDB path is REQUIRED - no default paths allowed! "
            "This prevents accidental creation of 'chromadb_data' in random directories."
        )
    
    path_str = str(chroma_path)
    
    # Ensure the path is absolute to avoid relative path issues
    path_obj = Path(path_str)
    if not path_obj.is_absolute():
        raise ValueError(
            f"ChromaDB path must be absolute, got relative path: {path_str}. "
            "Use Config.get_chapter_path() to get proper absolute paths."
        )
    
    if path_str not in _clients:
        # Create with explicit path - NEVER use defaults
        _clients[path_str] = chromadb.PersistentClient(path=path_str)
    
    return _clients[path_str]