"""
File storage utilities for OCR service
Handles saving and managing uploaded files for processing
"""
import os
import shutil
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class FileStorageManager:
    """
    Manages file storage for OCR processing

    Features:
    - Secure file storage with task-based organization
    - Path traversal prevention
    - Automatic directory creation
    - File cleanup support
    """

    def __init__(self, base_upload_dir: str = "/tmp/ocr-uploads"):
        """
        Initialize file storage manager

        Args:
            base_upload_dir: Base directory for file uploads
        """
        self.base_upload_dir = Path(base_upload_dir)
        self._ensure_base_dir()

    def _ensure_base_dir(self):
        """Ensure base upload directory exists"""
        try:
            self.base_upload_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"File storage base directory: {self.base_upload_dir}")
        except Exception as e:
            logger.error(f"Failed to create base directory: {e}")
            raise

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal attacks

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove path separators and parent directory references
        filename = os.path.basename(filename)
        filename = filename.replace("..", "")
        filename = filename.replace("/", "")
        filename = filename.replace("\\", "")

        return filename

    def get_task_directory(self, task_id: str) -> Path:
        """
        Get directory path for a specific task

        Args:
            task_id: Task identifier

        Returns:
            Path to task directory
        """
        # Validate task_id to prevent path traversal
        if not task_id or ".." in task_id or "/" in task_id or "\\" in task_id:
            raise ValueError(f"Invalid task_id: {task_id}")

        task_dir = self.base_upload_dir / task_id
        return task_dir

    def save_file(
        self,
        task_id: str,
        filename: str,
        content: bytes
    ) -> str:
        """
        Save uploaded file to task directory

        Args:
            task_id: Task identifier
            filename: Original filename
            content: File content bytes

        Returns:
            Absolute path to saved file
        """
        # Create task directory
        task_dir = self.get_task_directory(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        if not safe_filename:
            safe_filename = "document"

        # Save file
        file_path = task_dir / safe_filename

        try:
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Saved file for task {task_id}: {file_path}")
            return str(file_path.absolute())

        except Exception as e:
            logger.error(f"Failed to save file for task {task_id}: {e}")
            raise

    def get_file_path(self, task_id: str, filename: Optional[str] = None) -> Optional[str]:
        """
        Get path to stored file for a task

        Args:
            task_id: Task identifier
            filename: Optional specific filename to retrieve

        Returns:
            Absolute path to file or None if not found
        """
        task_dir = self.get_task_directory(task_id)

        if not task_dir.exists():
            return None

        if filename:
            # Get specific file
            safe_filename = self._sanitize_filename(filename)
            file_path = task_dir / safe_filename
            return str(file_path.absolute()) if file_path.exists() else None
        else:
            # Get first file in directory
            files = list(task_dir.iterdir())
            if files:
                return str(files[0].absolute())
            return None

    def cleanup_task_files(self, task_id: str) -> bool:
        """
        Clean up all files for a task

        Args:
            task_id: Task identifier

        Returns:
            True if cleanup successful
        """
        task_dir = self.get_task_directory(task_id)

        if not task_dir.exists():
            logger.info(f"Task directory does not exist: {task_id}")
            return True

        try:
            shutil.rmtree(task_dir)
            logger.info(f"Cleaned up files for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup files for task {task_id}: {e}")
            return False

    def file_exists(self, task_id: str) -> bool:
        """
        Check if file exists for task

        Args:
            task_id: Task identifier

        Returns:
            True if file exists
        """
        task_dir = self.get_task_directory(task_id)

        if not task_dir.exists():
            return False

        # Check if directory has any files
        files = list(task_dir.iterdir())
        return len(files) > 0


# Global file storage manager instance
_file_storage_manager: Optional[FileStorageManager] = None


def get_file_storage_manager() -> FileStorageManager:
    """Get global file storage manager instance"""
    global _file_storage_manager

    if _file_storage_manager is None:
        upload_dir = os.getenv("UPLOAD_DIR", "/tmp/ocr-uploads")
        _file_storage_manager = FileStorageManager(upload_dir)

    return _file_storage_manager
