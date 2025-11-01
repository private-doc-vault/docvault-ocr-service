"""
Validators for OCR service
"""
from typing import Optional
import os
from fastapi import HTTPException, status

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Supported file types
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
}

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
}

# Forbidden paths that should never be accessible
FORBIDDEN_PATHS = {
    "/etc/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/boot/",
    "/root/",
    "/sys/",
    "/proc/",
}

# Allowed paths (whitelist for shared storage)
ALLOWED_PATHS = {
    "/var/www/html/storage/",  # Shared storage with backend
}


def validate_file_type(filename: Optional[str], content_type: Optional[str]) -> bool:
    """
    Validate that the file type is supported

    Args:
        filename: Name of the file
        content_type: MIME type of the file

    Returns:
        True if file type is supported, False otherwise
    """
    if not filename:
        return False

    # Check file extension
    file_ext = None
    if "." in filename:
        file_ext = "." + filename.rsplit(".", 1)[1].lower()

    ext_valid = file_ext in SUPPORTED_EXTENSIONS if file_ext else False

    # Check MIME type
    mime_valid = content_type in SUPPORTED_MIME_TYPES if content_type else False

    # Accept if either extension or MIME type is valid
    return ext_valid or mime_valid


def validate_file_size(file_size: int) -> bool:
    """
    Validate that the file size is within limits

    Args:
        file_size: Size of the file in bytes

    Returns:
        True if file size is acceptable, False otherwise
    """
    return 0 < file_size <= MAX_FILE_SIZE


def validate_file_path(file_path: str) -> str:
    """
    Validate and sanitize file path to prevent security issues

    This function prevents:
    - Path traversal attacks (../)
    - Access to system directories
    - Symlink attacks
    - Arbitrary file access

    Args:
        file_path: The file path to validate

    Returns:
        Sanitized absolute file path

    Raises:
        HTTPException: If path is invalid or forbidden
    """
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid path", "detail": "File path cannot be empty"}
        )

    # Resolve to absolute path and normalize (removes ../, ./, etc.)
    try:
        abs_path = os.path.abspath(file_path)
        real_path = os.path.realpath(file_path)
    except (ValueError, OSError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid path", "detail": f"Cannot resolve path: {str(e)}"}
        )

    # Check if path contains traversal attempts
    if ".." in file_path:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Forbidden path", "detail": "Path traversal attempts are not allowed"}
        )

    # Check if path is in allowed paths (whitelist takes precedence)
    is_allowed = False
    for allowed_path in ALLOWED_PATHS:
        if real_path.startswith(allowed_path):
            is_allowed = True
            break

    # If not in allowed paths, check against forbidden paths
    if not is_allowed:
        for forbidden_path in FORBIDDEN_PATHS:
            if real_path.startswith(forbidden_path):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Forbidden path", "detail": f"Access to {forbidden_path} is not allowed"}
                )

    # Verify symlink doesn't point outside allowed directories
    if os.path.islink(file_path):
        if abs_path != real_path:
            # Symlink points to different location, check if it's trying to escape
            link_target = os.readlink(file_path)
            if link_target.startswith('/') or '..' in link_target:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Forbidden symlink", "detail": "Symlinks pointing outside allowed paths are not permitted"}
                )

    # Verify it's not trying to access /app source code
    if real_path.startswith('/app/app/'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Forbidden path", "detail": "Access to application source code is not allowed"}
        )

    return abs_path
