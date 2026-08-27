"""
R2 全链路验证：bucket 访问、upload、download、presigned URL、delete
在 Modal 上运行（使用 r2-storage-config secret）
"""
import modal
import json

image = modal.Image.debian_slim().pip_install("boto3", "requests")

app = modal.App("r2-verify", image=image)


@app.function(
    secrets=[modal.Secret.from_name("r2-storage-config")],
    timeout=120,
)
def verify_r2():
    import os
    import boto3
    import base64
    import json
    from botocore.exceptions import ClientError

    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    result = {
        "config": {
            "endpoint_configured": bool(endpoint),
            "access_key_configured": bool(access_key),
            "secret_key_configured": bool(secret_key),
            "bucket": bucket,
        }
    }

    if not all([endpoint, access_key, secret_key, bucket]):
        result["error"] = "R2 not fully configured"
        return result

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    # 1. Bucket 访问
    try:
        client.head_bucket(Bucket=bucket)
        result["bucket_access"] = "OK"
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        result["bucket_access"] = f"FAILED: {code}"
        if code in ("404", "NoSuchBucket"):
            result["error"] = f"Bucket '{bucket}' does not exist. Create it in Cloudflare R2 dashboard."
        return result
    except Exception as e:
        result["bucket_access"] = f"ERROR: {e}"
        return result

    # 2. Upload（测试文件，小样本）
    test_key = "test/verify/sample_test.wav"
    test_data = b"RIFF" + b"\x00" * 1000  # 伪 WAV 头 + 数据
    try:
        client.put_object(
            Bucket=bucket,
            Key=test_key,
            Body=test_data,
            ContentType="audio/wav",
        )
        result["upload"] = "OK"
    except Exception as e:
        result["upload"] = f"FAILED: {e}"
        return result

    # 3. Download / Head
    try:
        head = client.head_object(Bucket=bucket, Key=test_key)
        result["download"] = {
            "status": "OK",
            "size": head.get("ContentLength", 0),
            "content_type": head.get("ContentType", ""),
        }
    except Exception as e:
        result["download"] = f"FAILED: {e}"

    # 4. Presigned URL
    try:
        presigned = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": test_key},
            ExpiresIn=600,
        )
        # 验证 presigned URL 可访问
        import requests
        resp = requests.get(presigned, timeout=30)
        result["presigned_url"] = {
            "status": "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}",
            "size_downloaded": len(resp.content) if resp.status_code == 200 else 0,
        }
    except Exception as e:
        result["presigned_url"] = f"FAILED: {e}"

    # 5. Delete
    try:
        client.delete_object(Bucket=bucket, Key=test_key)
        # 验证已删除
        try:
            client.head_object(Bucket=bucket, Key=test_key)
            result["delete"] = "FAILED: object still exists"
        except ClientError:
            result["delete"] = "OK"
        except Exception:
            result["delete"] = "OK (head error)"
    except Exception as e:
        result["delete"] = f"FAILED: {e}"

    return result


@app.local_entrypoint()
def main():
    result = verify_r2.remote()
    print("=" * 50)
    print("R2 FULL-CHAIN VERIFICATION")
    print("=" * 50)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()