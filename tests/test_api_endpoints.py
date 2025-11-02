"""
Tests for OCR Service API Endpoints
Following TDD methodology - these tests define the expected behavior
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
import io
from PIL import Image


@pytest.mark.usefixtures("initialize_test_app")
class TestHealthEndpoints:
    """Test health check and status endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns service info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "status" in data
        assert data["status"] == "running"

    def test_health_check_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ocr"


@pytest.mark.usefixtures("initialize_test_app")
class TestOCRProcessEndpoints:
    """Test OCR processing endpoints"""

    def test_process_image_endpoint_exists(self, client):
        """Test that POST /api/v1/ocr/process endpoint exists"""
        # This test will initially fail - we need to create this endpoint
        response = client.post("/api/v1/ocr/process")
        # Should return 422 (validation error) not 404 (not found)
        assert response.status_code != 404

    def test_process_image_requires_file(self, client):
        """Test that process endpoint requires a file"""
        response = client.post("/api/v1/ocr/process")
        assert response.status_code == 422  # Unprocessable Entity
        data = response.json()
        assert "detail" in data

    def test_process_image_with_valid_image(self, client):
        """Test OCR processing with a valid image file"""
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")}
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] in ["queued", "processing", "completed"]

    def test_process_image_with_language_parameter(self, client):
        """Test OCR processing with language specification"""
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")},
            data={"language": "eng"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_process_image_with_invalid_file_type(self, client):
        """Test that invalid file types are rejected"""
        invalid_file = io.BytesIO(b"not an image")

        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.txt", invalid_file, "text/plain")}
        )

        assert response.status_code in [400, 422]  # Validation errors can be 400 or 422
        data = response.json()
        assert "error" in data or "detail" in data

    def test_process_image_with_oversized_file(self, client):
        """Test that oversized files are rejected"""
        # Create a large image that exceeds size limit
        large_img = Image.new('RGB', (10000, 10000), color='white')
        img_bytes = io.BytesIO()
        large_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("large.png", img_bytes, "image/png")}
        )

        # Should either accept it or return 413 (Payload Too Large) or 400
        assert response.status_code in [200, 400, 413]

    # NEW TESTS FOR FILE PATH-BASED PROCESSING
    # Following TDD - these will fail until routes.py is updated

    def test_process_with_file_path_instead_of_upload(self, client):
        """Test OCR processing using file_path parameter instead of file upload"""
        import tempfile
        import os

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            img = Image.new('RGB', (100, 100), color='white')
            img.save(tmp_file, format='PNG')
            file_path = tmp_file.name

        try:
            # Send file_path instead of file upload
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": file_path,
                    "language": "eng"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert "status" in data
            assert data["status"] in ["queued", "processing"]
        finally:
            # Cleanup
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_process_with_file_path_validates_file_exists(self, client):
        """Test that file_path validation checks if file exists"""
        response = client.post(
            "/api/v1/ocr/process",
            data={
                "file_path": "/nonexistent/path/to/file.pdf",
                "language": "eng"
            }
        )

        # Should return 400 Bad Request for non-existent file
        assert response.status_code in [400, 422]  # Validation errors can be 400 or 422
        data = response.json()
        assert "error" in data or "detail" in data
        assert "not found" in str(data).lower() or "does not exist" in str(data).lower()

    def test_process_with_file_path_prevents_path_traversal(self, client):
        """Test that file_path validation prevents path traversal attacks"""
        # Test various path traversal attempts
        malicious_paths = [
            "../../etc/passwd",
            "/etc/passwd",
            "../../../sensitive/file.pdf",
            "../../app/__init__.py"
        ]

        for malicious_path in malicious_paths:
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": malicious_path,
                    "language": "eng"
                }
            )

            # Should reject with 400 or 403
            assert response.status_code in [400, 403]
            data = response.json()
            assert "error" in data or "detail" in data

    def test_process_with_file_path_requires_allowed_extension(self, client):
        """Test that file_path validation checks file extension"""
        import tempfile
        import os

        # Create a temp file with invalid extension
        with tempfile.NamedTemporaryFile(mode='w', suffix='.exe', delete=False) as tmp_file:
            tmp_file.write("malicious content")
            file_path = tmp_file.name

        try:
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": file_path,
                    "language": "eng"
                }
            )

            # Should reject invalid file types
            assert response.status_code in [400, 422]  # Validation errors can be 400 or 422
            data = response.json()
            assert "error" in data or "detail" in data
        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_process_with_shared_storage_path(self, client):
        """Test processing file from shared storage directory"""
        import tempfile
        import os

        # Simulate shared storage path
        # In production this would be /var/www/html/storage/documents/...
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as tmp_file:
            # Create a simple PDF-like file
            tmp_file.write(b"%PDF-1.4\ntest content")
            file_path = tmp_file.name

        try:
            response = client.post(
                "/api/v1/ocr/process",
                data={
                    "file_path": file_path,
                    "language": "eng"
                }
            )

            # Should accept valid shared storage path
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_process_accepts_either_file_or_file_path(self, client):
        """Test that endpoint can accept either file upload OR file_path (backward compatibility)"""
        import tempfile
        import os

        # Test 1: File upload still works
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        response1 = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")}
        )
        assert response1.status_code == 200

        # Test 2: File path works
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            img = Image.new('RGB', (100, 100), color='white')
            img.save(tmp_file, format='PNG')
            file_path = tmp_file.name

        try:
            response2 = client.post(
                "/api/v1/ocr/process",
                data={"file_path": file_path}
            )
            assert response2.status_code == 200
        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_process_rejects_both_file_and_file_path(self, client):
        """Test that providing both file and file_path is rejected"""
        import tempfile

        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            file_path = tmp_file.name

        try:
            response = client.post(
                "/api/v1/ocr/process",
                files={"file": ("test.png", img_bytes, "image/png")},
                data={"file_path": file_path}
            )

            # Should reject ambiguous request
            assert response.status_code in [400, 422]  # Validation errors can be 400 or 422
            data = response.json()
            assert "error" in data or "detail" in data
        finally:
            import os
            if os.path.exists(file_path):
                os.unlink(file_path)


@pytest.mark.usefixtures("initialize_test_app")
class TestOCRStatusEndpoints:
    """Test OCR processing status endpoints"""

    def test_get_task_status_endpoint_exists(self, client):
        """Test that GET /api/v1/ocr/status/{task_id} endpoint exists"""
        response = client.get("/api/v1/ocr/status/test-task-id")
        # Should not return 404
        assert response.status_code != 404

    def test_get_task_status_with_valid_id(self, client):
        """Test retrieving status of a processing task"""
        # First create a task
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        create_response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")}
        )

        assert create_response.status_code == 200
        task_id = create_response.json()["task_id"]

        # Now check the status
        status_response = client.get(f"/api/v1/ocr/status/{task_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] in ["queued", "processing", "completed", "failed"]

    def test_get_task_status_with_invalid_id(self, client):
        """Test retrieving status with non-existent task ID"""
        response = client.get("/api/v1/ocr/status/invalid-task-id-12345")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data


@pytest.mark.usefixtures("initialize_test_app")
class TestOCRResultEndpoints:
    """Test OCR result retrieval endpoints"""

    def test_get_task_result_endpoint_exists(self, client):
        """Test that GET /api/v1/ocr/result/{task_id} endpoint exists"""
        response = client.get("/api/v1/ocr/result/test-task-id")
        assert response.status_code != 404

    def test_get_task_result_with_completed_task(self, client):
        """Test retrieving results of a completed OCR task"""
        # First create and process a task
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        create_response = client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.png", img_bytes, "image/png")}
        )

        task_id = create_response.json()["task_id"]

        # Get the result
        result_response = client.get(f"/api/v1/ocr/result/{task_id}")

        # Should return 200 if completed, or 202 if still processing
        assert result_response.status_code in [200, 202]

        if result_response.status_code == 200:
            data = result_response.json()
            assert "task_id" in data
            assert "text" in data
            assert "confidence" in data
            assert isinstance(data["text"], str)

    def test_get_task_result_with_invalid_id(self, client):
        """Test retrieving results with non-existent task ID"""
        response = client.get("/api/v1/ocr/result/invalid-task-id-67890")
        assert response.status_code == 404


@pytest.mark.usefixtures("initialize_test_app")
class TestBatchProcessingEndpoints:
    """Test batch OCR processing endpoints"""

    def test_batch_process_endpoint_exists(self, client):
        """Test that POST /api/v1/ocr/batch endpoint exists"""
        response = client.post("/api/v1/ocr/batch")
        assert response.status_code != 404

    def test_batch_process_with_multiple_files(self, client):
        """Test batch processing with multiple image files"""
        files = []
        for i in range(3):
            img = Image.new('RGB', (100, 100), color='white')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            files.append(("files", (f"test{i}.png", img_bytes, "image/png")))

        response = client.post("/api/v1/ocr/batch", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "batch_id" in data
        assert "task_ids" in data
        assert len(data["task_ids"]) == 3

    def test_batch_status_endpoint(self, client):
        """Test retrieving status of batch processing"""
        # Create a batch
        files = []
        for i in range(2):
            img = Image.new('RGB', (100, 100), color='white')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            files.append(("files", (f"test{i}.png", img_bytes, "image/png")))

        create_response = client.post("/api/v1/ocr/batch", files=files)
        batch_id = create_response.json()["batch_id"]

        # Get batch status
        status_response = client.get(f"/api/v1/ocr/batch/{batch_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        assert "batch_id" in data
        assert "total" in data
        assert "completed" in data
        assert "failed" in data


@pytest.mark.usefixtures("initialize_test_app")
class TestSupportedLanguagesEndpoint:
    """Test endpoint for listing supported OCR languages"""

    def test_supported_languages_endpoint(self, client):
        """Test GET /api/v1/ocr/languages endpoint"""
        response = client.get("/api/v1/ocr/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert isinstance(data["languages"], list)
        assert len(data["languages"]) > 0
        # Should at least support English
        language_codes = [lang["code"] for lang in data["languages"]]
        assert "eng" in language_codes
