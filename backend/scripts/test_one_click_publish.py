"""
One-Click Publish API Testing Script

Tests the one-click publish endpoints:
- GET /api/v1/publish/platforms
- POST /api/v1/publish/auth/{platform}
- POST /api/v1/publish/upload
- GET /api/v1/publish/status/{task_id}

Run with: python scripts/test_one_click_publish.py
"""

import asyncio
import httpx
import sys


BASE_URL = "http://localhost:8000"


async def test_get_platforms():
    """Test GET /api/v1/publish/platforms"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/publish/platforms")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "platforms" in data
        assert len(data["platforms"]) >= 3
        print(f"✅ GET /api/v1/publish/platforms: {len(data['platforms'])} platforms")
        return data


async def test_auth_platform(platform: str = "youtube"):
    """Test POST /api/v1/publish/auth/{platform}"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/publish/auth/{platform}",
            json={"redirect_uri": "http://localhost:3000/auth/callback"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✅ POST /api/v1/publish/auth/{platform}: {data['status']} - {data['message']}")
        return data


async def test_upload_video():
    """Test POST /api/v1/publish/upload"""
    async with httpx.AsyncClient() as client:
        payload = {
            "video_url": "/results/mock_video.mp4",
            "platforms": ["youtube", "bilibili"],
            "title": "Test Music Video",
            "description": "A test video for one-click publish",
            "tags": ["music", "test", "demo"],
            "privacy": "public",
            "youtube_category_id": "10",
            "bilibili_tid": 112,
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/publish/upload",
            json=payload,
            timeout=30.0
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "platforms" in data
        print(f"✅ POST /api/v1/publish/upload: task_id={data['task_id']}")
        return data


async def test_get_status(task_id: str):
    """Test GET /api/v1/publish/status/{task_id}"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/publish/status/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        print(f"✅ GET /api/v1/publish/status/{task_id}: {data['status']} ({data['progress']}%)")
        return data


async def main():
    """Run all tests"""
    print("=" * 60)
    print("One-Click Publish API Tests")
    print("=" * 60)
    
    try:
        # Test 1: Get platforms
        print("\n📋 Test 1: Get Platforms")
        await test_get_platforms()
        
        # Test 2: Auth platforms
        print("\n🔐 Test 2: Platform Authorization (Mock)")
        for platform in ["youtube", "tiktok", "bilibili"]:
            await test_auth_platform(platform)
        
        # Test 3: Upload video
        print("\n📤 Test 3: Upload Video")
        upload_result = await test_upload_video()
        task_id = upload_result["task_id"]
        
        # Test 4: Check status
        print("\n📊 Test 4: Check Status")
        await test_get_status(task_id)
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except httpx.ConnectError as e:
        print(f"\n❌ Connection error: {e}")
        print("Make sure the backend server is running: uvicorn main:app --reload")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())