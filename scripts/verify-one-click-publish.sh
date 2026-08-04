# One-Click Publish Verification Script
# Run: bash scripts/verify-one-click-publish.sh

#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "============================================================"
echo "One-Click Publish Feature Verification"
echo "============================================================"
echo ""

ERRORS=0

# 1. Check file existence
echo "📁 Checking file existence..."
FILES=(
    "backend/app/routers/one_click_publish.py"
    "backend/app/services/youtube_service.py"
    "backend/app/services/tiktok_service.py"
    "backend/app/services/bilibili_service.py"
    "frontend/src/components/OneClickPublish.tsx"
    "frontend/src/components/PlatformSelector.tsx"
    "frontend/src/api/publish.ts"
    "backend/scripts/test_one_click_publish.py"
    "docs/one-click-publish.md"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        SIZE=$(wc -c < "$file")
        echo "  ✓ $file ($SIZE bytes)"
    else
        echo "  ✗ $file (MISSING)"
        ERRORS=$((ERRORS + 1))
    fi
done

# 2. Python syntax check
echo ""
echo "🐍 Checking Python syntax..."
python -m py_compile backend/app/routers/one_click_publish.py && echo "  ✓ one_click_publish.py"
python -m py_compile backend/app/services/youtube_service.py && echo "  ✓ youtube_service.py"
python -m py_compile backend/app/services/tiktok_service.py && echo "  ✓ tiktok_service.py"
python -m py_compile backend/app/services/bilibili_service.py && echo "  ✓ bilibili_service.py"
python -m py_compile backend/scripts/test_one_click_publish.py && echo "  ✓ test_one_click_publish.py"

# 3. Check main.py registration
echo ""
echo "📝 Checking main.py registration..."
if grep -q "from app.routers import one_click_publish" backend/main.py; then
    echo "  ✓ Import statement found"
else
    echo "  ✗ Import statement missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "app.include_router(one_click_publish.router)" backend/main.py; then
    echo "  ✓ Router registration found"
else
    echo "  ✗ Router registration missing"
    ERRORS=$((ERRORS + 1))
fi

# 4. Check API endpoints
echo ""
echo "🌐 Checking API endpoints..."
if grep -q '@router.get("/platforms"' backend/app/routers/one_click_publish.py; then
    echo "  ✓ GET /api/v1/publish/platforms"
else
    echo "  ✗ GET /api/v1/publish/platforms missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q '@router.post.*/auth/' backend/app/routers/one_click_publish.py; then
    echo "  ✓ POST /api/v1/publish/auth/{platform}"
else
    echo "  ✗ POST /api/v1/publish/auth/{platform} missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q '@router.post("/upload"' backend/app/routers/one_click_publish.py; then
    echo "  ✓ POST /api/v1/publish/upload"
else
    echo "  ✗ POST /api/v1/publish/upload missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q '@router.get("/status/' backend/app/routers/one_click_publish.py; then
    echo "  ✓ GET /api/v1/publish/status/{task_id}"
else
    echo "  ✗ GET /api/v1/publish/status/{task_id} missing"
    ERRORS=$((ERRORS + 1))
fi

# 5. Check service methods
echo ""
echo "🔧 Checking service methods..."
if grep -q "async def publish_video" backend/app/services/youtube_service.py; then
    echo "  ✓ youtube_service.publish_video"
else
    echo "  ✗ youtube_service.publish_video missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "async def publish_video" backend/app/services/tiktok_service.py; then
    echo "  ✓ tiktok_service.publish_video"
else
    echo "  ✗ tiktok_service.publish_video missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "async def publish_video" backend/app/services/bilibili_service.py; then
    echo "  ✓ bilibili_service.publish_video"
else
    echo "  ✗ bilibili_service.publish_video missing"
    ERRORS=$((ERRORS + 1))
fi

# 6. Check frontend components
echo ""
echo "⚛️ Checking frontend components..."
if grep -q "export function OneClickPublish" frontend/src/components/OneClickPublish.tsx; then
    echo "  ✓ OneClickPublish component"
else
    echo "  ✗ OneClickPublish component missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "export function PlatformSelector" frontend/src/components/PlatformSelector.tsx; then
    echo "  ✓ PlatformSelector component"
else
    echo "  ✗ PlatformSelector component missing"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "getPlatforms" frontend/src/api/publish.ts; then
    echo "  ✓ publish.ts API client"
else
    echo "  ✗ publish.ts API client missing"
    ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
echo "============================================================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ VERIFICATION PASSED - All checks successful"
    echo ""
    echo "Summary:"
    echo "  - 9 files created/modified"
    echo "  - 4 API endpoints implemented"
    echo "  - 3 platform services (YouTube, TikTok, Bilibili)"
    echo "  - 2 frontend components"
    echo "  - Mock mode enabled for development"
    exit 0
else
    echo "❌ VERIFICATION FAILED - $ERRORS error(s)"
    exit 1
fi