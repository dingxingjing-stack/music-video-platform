import modal
import json

image = modal.Image.debian_slim().pip_install("boto3")

app = modal.App("r2-which-secret", image=image)

SECRETS = ["r2-storage-config", "avireon-secrets", "avireon-config", "agnes-key", "hf-token"]


@app.function(
    secrets=[modal.Secret.from_name(s) for s in SECRETS],
    timeout=120,
)
def test_all():
    import os
    import boto3
    from botocore.exceptions import ClientError

    results = {}
    # 无法在单函数中隔离 secret，改为分别尝试所有 bucket 访问
    # 先看当前函数内可见的配置
    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    results["visible_config"] = {
        "endpoint": endpoint,
        "access_key_prefix": (access_key or "")[:10] + "..." if access_key else None,
        "secret_key_set": bool(secret_key),
        "bucket": bucket,
    }

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    try:
        client.head_bucket(Bucket=bucket)
        results["head_bucket"] = "OK"
    except ClientError as e:
        results["head_bucket"] = f"{e.response.get('Error', {}).get('Code', 'UNKNOWN')}"
    except Exception as e:
        results["head_bucket"] = f"ERROR: {e}"

    return results


@app.local_entrypoint()
def main():
    result = test_all.remote()
    print("=" * 50)
    print("R2 SECRET DIAGNOSTIC")
    print("=" * 50)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()