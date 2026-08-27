import modal

image = modal.Image.debian_slim()

app = modal.App("inspect-all-secrets", image=image)

@app.function(
    secrets=[
        modal.Secret.from_name("r2-storage-config"),
        modal.Secret.from_name("avireon-secrets"),
        modal.Secret.from_name("avireon-config"),
        modal.Secret.from_name("agnes-key"),
        modal.Secret.from_name("hf-token"),
    ]
)
def inspect():
    import os
    result = {}
    for name in ["r2-storage-config", "avireon-secrets", "avireon-config", "agnes-key", "hf-token"]:
        keys = {}
        for env_var in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_DOMAIN",
                        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT", "S3_ENDPOINT", "S3_BUCKET",
                        "SUPABASE_URL", "HF_TOKEN", "AGNES_API_KEY"]:
            val = os.getenv(env_var)
            if val:
                keys[env_var] = "SET" if env_var not in ("R2_ENDPOINT", "S3_ENDPOINT", "AWS_ENDPOINT", "SUPABASE_URL") else val
        if keys:
            result[name] = keys
    return result

@app.local_entrypoint()
def main():
    result = inspect.remote()
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))