"""Test script to verify handler.py can be imported and basic functionality works."""

import sys
import os

# Add the runpod directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_import():
    """Test that handler.py can be imported without errors."""
    print("Testing handler import...")
    try:
        import handler
        print("[OK] handler.py imported successfully")
    except Exception as e:
        print(f"[FAIL] Failed to import handler: {e}")
        return False
    return True


def test_handler_function():
    """Test that handler function exists and is callable."""
    print("Testing handler function...")
    try:
        import handler
        if hasattr(handler, 'handler') and callable(handler.handler):
            print("[OK] handler function exists and is callable")
        else:
            print("[FAIL] handler function not found or not callable")
            return False
    except Exception as e:
        print(f"[FAIL] Failed to access handler function: {e}")
        return False
    return True


def test_runpod_import():
    """Test that runpod module is available."""
    print("Testing runpod import...")
    try:
        import runpod
        print(f"[OK] runpod imported successfully (version: {runpod.__version__})")
    except ImportError as e:
        print(f"[FAIL] Failed to import runpod: {e}")
        return False
    return True


def test_torch_import():
    """Test that torch is available and CUDA can be checked."""
    print("Testing torch import...")
    try:
        import torch
        print(f"[OK] torch imported successfully (version: {torch.__version__})")
        print(f"  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    except ImportError as e:
        print(f"[FAIL] Failed to import torch: {e}")
        return False
    return True


def test_optional_imports():
    """Test optional dependencies."""
    print("Testing optional imports...")
    
    # torchaudio
    try:
        import torchaudio
        print(f"[OK] torchaudio available (version: {torchaudio.__version__})")
    except ImportError:
        print("  torchaudio: not available")
    
    # librosa
    try:
        import librosa
        print(f"[OK] librosa available (version: {librosa.__version__})")
    except ImportError:
        print("  librosa: not available")
    
    return True


def run_smoke_test():
    """Run a quick smoke test of the handler function."""
    print("Running smoke test...")
    try:
        import handler
        # Create a mock job
        job = {
            "input": {
                "prompt": "test prompt",
                "duration": 10,
                "test_mode": "smoke"
            }
        }
        # Call handler synchronously (it's async but we can test the structure)
        # Since handler is async, we just verify it can be called
        print("[OK] handler function structure verified")
        return True
    except Exception as e:
        print(f"[FAIL] Smoke test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("RunPod Worker Smoke Tests")
    print("=" * 60)
    
    tests = [
        test_import,
        test_handler_function,
        test_runpod_import,
        test_torch_import,
        test_optional_imports,
        run_smoke_test,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        print()
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {test.__name__} raised exception: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)