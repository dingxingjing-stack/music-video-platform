import modal
import json

image = modal.Image.debian_slim().pip_install("boto3")

app = modal.App("r2-secret-tests", image=image)


def _test_r2():
    import os
    import boto3
    from botocore.exceptions import ClientError

    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    info = {
        "endpoint": endpoint,
        "access_key_prefix": (access_key or "")[:12] + "..." if access_key else None,
        "secret_key_set": bool(secret_key),
        "bucket": bucket,
    }

    if not all([endpoint, access_key, secret_key, bucket]):
        info["head_bucket"] = "SKIPPED (missing config)"
        return info

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    try:
        client.head_bucket(Bucket=bucket)
        info["head_bucket"] = "OK"
    except ClientError as e:
        info["head_bucket"] = e.response.get("Error", {}).get("Code", "UNKNOWN")
    except Exception as e:
        info["head_bucket"] = f"ERROR: {e}"
    return info


@app.function(secrets=[modal.Secret.from_name("r2-storage-config")], timeout=120)
def test_r2_storage():
    return _test_r2()


@app.function(secrets=[modal.Secret.from_name("avireon-secrets")], timeout=120)
def test_avireon_secrets():
    return _test_r2()


@app.function(secrets=[modal.Secret.from_name("avireon-config")], timeout=120)
def test_avireon_config():
    return _test_r2()


@app.function(secrets=[modal.Secret.from_name("agnes-key")], timeout=120)
def test_agnes_key():
    return _test_r2()


@app.function(secrets=[modal.Secret.from_name("hf-token")], timeout=120)
def test_hf_token():
    return _test_r2()


@app.local_entrypoint()
def main():
    results = {
        "r2-storage-config": test_r2_storage.remote(),
        "avireon-secrets": test_avireon_secrets.remote(),
        "avireon-config": test_avireon_config.remote(),
        "agnes-key": test_agnes_key.remote(),
        "hf-token": test_hf_token.remote(),
    }
    print("=" * 50)
    print("R2 PER-SECRET DIAGNOSTIC")
    print("=" * 50)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()