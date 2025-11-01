"""
Integration tests for shared storage file path processing

Tests the OCR service's ability to:
1. Accept file_path parameter instead of file upload
2. Read files from shared storage path
3. Process files without creating duplicates
4. Validate file paths for security
"""
import pytest
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
import io

from app.main import app

client = TestClient(app)


class TestSharedStorageIntegration:
    """Integration tests for shared storage file processing"""

    @pytest.fixture
    def shared_storage_dir(self):
        """Create a temporary directory to simulate shared storage"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def test_image_file(self, shared_storage_dir):
        """Create a test image in shared storage"""
        file_path = os.path.join(shared_storage_dir, "test_document.png")

        # Create a simple test image
        img = Image.new('RGB', (200, 200), color='white')
        img.save(file_path)

        return file_path

    @pytest.fixture
    def test_pdf_file(self, shared_storage_dir):
        """Create a test PDF in shared storage"""
        file_path = os.path.join(shared_storage_dir, "test_document.pdf")

        # Create minimal valid PDF
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 2\ntrailer<</Size 2/Root 1 0 R>>\nstartxref\n50\n%%EOF"
        with open(file_path, 'wb') as f:
            f.write(pdf_content)

        return file_path

    def test_process_with_file_path_from_shared_storage(self, test_image_file):
        """Test processing file using file_path parameter"""
        # GIVEN: A file in shared storage
        assert os.path.exists(test_image_file)
        initial_size = os.path.getsize(test_image_file)

        # WHEN: Processing with file_path
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": test_image_file,
                "language": "eng"
            }
        )

        # THEN: Should succeed
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "queued"

        # AND: Original file should remain unchanged
        assert os.path.exists(test_image_file)
        assert os.path.getsize(test_image_file) == initial_size

    def test_no_file_duplication_with_file_path(self, test_image_file, shared_storage_dir):
        """Test that using file_path does not create duplicates"""
        # GIVEN: A file in shared storage
        initial_file_count = len(os.listdir(shared_storage_dir))

        # WHEN: Processing with file_path
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": test_image_file,
                "language": "eng"
            }
        )

        # THEN: No additional files should be created
        assert response.status_code == 200
        final_file_count = len(os.listdir(shared_storage_dir))
        assert final_file_count == initial_file_count, "No duplicate files should be created"

    def test_file_path_validation_prevents_traversal(self):
        """Test that path traversal attempts are blocked"""
        malicious_paths = [
            "../../etc/passwd",
            "/etc/passwd",
            "../../../sensitive/data.pdf",
            "../../app/main.py"
        ]

        for malicious_path in malicious_paths:
            # WHEN: Attempting to use malicious path
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": malicious_path,
                    "language": "eng"
                }
            )

            # THEN: Should be rejected
            assert response.status_code in [400, 403], f"Path {malicious_path} should be rejected"
            data = response.json()
            assert "error" in data or "detail" in data

    def test_file_path_validation_requires_existing_file(self, shared_storage_dir):
        """Test that non-existent files are rejected"""
        # GIVEN: A path to non-existent file
        fake_path = os.path.join(shared_storage_dir, "nonexistent.pdf")
        assert not os.path.exists(fake_path)

        # WHEN: Attempting to process non-existent file
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": fake_path,
                "language": "eng"
            }
        )

        # THEN: Should be rejected
        assert response.status_code == 400
        data = response.json()
        assert "not found" in str(data).lower() or "does not exist" in str(data).lower()

    def test_file_path_validation_checks_extension(self, shared_storage_dir):
        """Test that invalid file extensions are rejected"""
        # GIVEN: A file with invalid extension
        invalid_file = os.path.join(shared_storage_dir, "malicious.exe")
        with open(invalid_file, 'w') as f:
            f.write("malicious content")

        # WHEN: Attempting to process invalid file type
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": invalid_file,
                "language": "eng"
            }
        )

        # THEN: Should be rejected
        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    def test_backward_compatibility_file_upload_still_works(self):
        """Test that old file upload method still works"""
        # GIVEN: A file upload (old method)
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # WHEN: Uploading file
        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")},
            data={"language": "eng"}
        )

        # THEN: Should still work
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_both_file_and_file_path_rejected(self, test_image_file):
        """Test that providing both file and file_path is rejected"""
        # GIVEN: Both file upload and file_path
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # WHEN: Sending both parameters
        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")},
            data={
                "file_path": test_image_file,
                "language": "eng"
            }
        )

        # THEN: Should be rejected
        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    def test_multiple_files_can_share_same_storage(self, shared_storage_dir):
        """Test that multiple files can coexist in shared storage"""
        # GIVEN: Multiple files in shared storage
        file_paths = []
        for i in range(3):
            file_path = os.path.join(shared_storage_dir, f"test_{i}.png")
            img = Image.new('RGB', (100, 100), color='white')
            img.save(file_path)
            file_paths.append(file_path)

        # WHEN: Processing all files
        task_ids = []
        for file_path in file_paths:
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": file_path,
                    "language": "eng"
                }
            )
            assert response.status_code == 200
            task_ids.append(response.json()["task_id"])

        # THEN: All files should remain in storage
        for file_path in file_paths:
            assert os.path.exists(file_path)

        # AND: All tasks should be unique
        assert len(task_ids) == len(set(task_ids)), "All task IDs should be unique"

    def test_absolute_paths_are_accepted(self, test_image_file):
        """Test that absolute paths work correctly"""
        # GIVEN: An absolute path
        absolute_path = os.path.abspath(test_image_file)
        assert os.path.isabs(absolute_path)

        # WHEN: Processing with absolute path
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": absolute_path,
                "language": "eng"
            }
        )

        # THEN: Should succeed
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_relative_paths_work_within_allowed_directories(self, shared_storage_dir):
        """Test that relative paths within allowed directories work"""
        # GIVEN: A file in a subdirectory
        subdir = os.path.join(shared_storage_dir, "subdir")
        os.makedirs(subdir)
        file_path = os.path.join(subdir, "test.png")

        img = Image.new('RGB', (100, 100), color='white')
        img.save(file_path)

        # WHEN: Processing with path
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": file_path,
                "language": "eng"
            }
        )

        # THEN: Should succeed
        assert response.status_code == 200

    def test_symlinks_are_validated(self, test_image_file, shared_storage_dir):
        """Test that symlinks pointing outside storage are rejected"""
        # GIVEN: A symlink pointing to test file
        symlink_path = os.path.join(shared_storage_dir, "symlink.png")

        # Create symlink to outside directory (if not on Windows)
        if os.name != 'nt':
            try:
                os.symlink("/etc/passwd", symlink_path)

                # WHEN: Attempting to process symlink
                response = client.post(
                    "/api/v1/ocr/process",
                    data={
                        "file_path": symlink_path,
                        "language": "eng"
                    }
                )

                # THEN: Should be rejected
                assert response.status_code in [400, 403]
            except OSError:
                # Skip if symlink creation fails
                pytest.skip("Could not create symlink for testing")


class TestSharedStorageCleanupBehavior:
    """Test that OCR service does NOT clean up files (backend's responsibility)"""

    @pytest.fixture
    def test_file_with_tracking(self, shared_storage_dir):
        """Create a test file that we can track"""
        file_path = os.path.join(shared_storage_dir, "tracked_file.png")
        img = Image.new('RGB', (100, 100), color='white')
        img.save(file_path)
        return file_path

    def test_files_not_cleaned_up_after_processing(self, test_file_with_tracking):
        """Test that files remain after OCR processing"""
        # GIVEN: A file in shared storage
        assert os.path.exists(test_file_with_tracking)
        file_mtime = os.path.getmtime(test_file_with_tracking)

        # WHEN: Processing the file
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": test_file_with_tracking,
                "language": "eng"
            }
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # THEN: File should STILL exist (not cleaned up)
        assert os.path.exists(test_file_with_tracking), "File should remain after processing"

        # AND: File should not be modified
        assert os.path.getmtime(test_file_with_tracking) == file_mtime, "File should not be modified"
