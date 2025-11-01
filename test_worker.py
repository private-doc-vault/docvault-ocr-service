"""
Test script for OCR Worker implementation
Tests Redis connection, queue operations, and task processing
"""
import asyncio
import httpx
import time
from pathlib import Path


async def test_redis_connection():
    """Test 5.1: Test Redis connection and queue initialization"""
    print("\n=== Test 5.1: Redis Connection and Queue Initialization ===")

    try:
        url = "http://localhost:8001/health"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                print("✓ OCR Service health check passed")
                print(f"  Response: {response.json()}")
                return True
            else:
                print(f"✗ OCR Service health check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"✗ Failed to connect to OCR service: {e}")
        return False


async def test_upload_document():
    """Test 5.2: Upload a test document and verify task is queued"""
    print("\n=== Test 5.2: Upload Document and Queue Verification ===")

    # Create a simple test text file (simulating a document)
    test_file_path = Path("/tmp/test_document.txt")
    test_file_path.write_text("This is a test document for OCR processing.")

    try:
        url = "http://localhost:8001/api/v1/ocr/process"

        # Upload file
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(test_file_path, "rb") as f:
                files = {"file": ("test_document.txt", f, "text/plain")}
                data = {"language": "eng"}
                response = await client.post(url, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            task_id = result.get("task_id")
            print(f"✓ Document uploaded successfully")
            print(f"  Task ID: {task_id}")
            print(f"  Status: {result.get('status')}")
            return task_id
        else:
            print(f"✗ Upload failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None

    except Exception as e:
        print(f"✗ Upload error: {e}")
        return None
    finally:
        # Cleanup test file
        if test_file_path.exists():
            test_file_path.unlink()


async def test_task_status_transitions(task_id: str):
    """Test 5.4: Check task status transitions"""
    print("\n=== Test 5.4: Task Status Transitions ===")

    if not task_id:
        print("✗ No task ID provided")
        return False

    url = f"http://localhost:8001/api/v1/ocr/status/{task_id}"

    # Poll status for up to 30 seconds
    max_attempts = 30
    attempt = 0

    statuses_seen = []

    try:
        async with httpx.AsyncClient() as client:
            while attempt < max_attempts:
                response = await client.get(url)

                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status")
                    progress = result.get("progress", 0)
                    message = result.get("message", "")

                    if status not in statuses_seen:
                        statuses_seen.append(status)
                        print(f"  [{attempt}s] Status: {status} | Progress: {progress}% | {message}")

                    # Check if completed or failed
                    if status == "COMPLETED":
                        print(f"✓ Task completed successfully")
                        print(f"  Status transitions: {' → '.join(statuses_seen)}")
                        return True
                    elif status == "FAILED":
                        print(f"✗ Task failed")
                        print(f"  Status transitions: {' → '.join(statuses_seen)}")
                        return False

                attempt += 1
                await asyncio.sleep(1)

            print(f"✗ Task did not complete within {max_attempts} seconds")
            print(f"  Status transitions: {' → '.join(statuses_seen)}")
            return False

    except Exception as e:
        print(f"✗ Error checking status: {e}")
        return False


async def test_get_result(task_id: str):
    """Test 5.5: Verify OCR result is retrievable"""
    print("\n=== Test 5.5: Retrieve OCR Result ===")

    if not task_id:
        print("✗ No task ID provided")
        return False

    url = f"http://localhost:8001/api/v1/ocr/result/{task_id}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

            if response.status_code == 200:
                result = response.json()
                print(f"✓ Result retrieved successfully")
                print(f"  Text length: {len(result.get('text', ''))} characters")
                print(f"  Confidence: {result.get('confidence', 0):.2f}%")
                print(f"  Language: {result.get('language')}")
                print(f"  Page count: {result.get('page_count')}")
                print(f"  Processing time: {result.get('processing_time', 0):.2f}s")

                # Show first 100 chars of extracted text
                text = result.get('text', '')
                if text:
                    preview = text[:100] + "..." if len(text) > 100 else text
                    print(f"  Text preview: {preview}")

                return True
            elif response.status_code == 202:
                print(f"✓ Task still processing (202)")
                return False
            else:
                print(f"✗ Failed to retrieve result: {response.status_code}")
                print(f"  Response: {response.text}")
                return False

    except Exception as e:
        print(f"✗ Error retrieving result: {e}")
        return False


async def test_queue_stats():
    """Test: Check Redis queue statistics"""
    print("\n=== Additional Test: Queue Statistics ===")

    # This would require direct Redis access or a new API endpoint
    # For now, we'll skip this test
    print("  (Skipped - requires Redis CLI access)")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("OCR Worker Implementation Tests")
    print("=" * 60)

    # Test 5.1: Redis connection
    if not await test_redis_connection():
        print("\n✗ Redis connection test failed. Exiting.")
        return

    await asyncio.sleep(1)

    # Test 5.2: Upload document
    task_id = await test_upload_document()
    if not task_id:
        print("\n✗ Document upload failed. Exiting.")
        return

    await asyncio.sleep(2)

    # Test 5.4: Status transitions
    completed = await test_task_status_transitions(task_id)

    if completed:
        await asyncio.sleep(1)

        # Test 5.5: Get result
        await test_get_result(task_id)

    # Additional tests
    await test_queue_stats()

    print("\n" + "=" * 60)
    print("Test Suite Completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
