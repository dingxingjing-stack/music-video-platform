import modal

image = modal.Image.debian_slim().pip_install("requests")

app = modal.App("inspect-secrets-2", image=image)

@app.function(
    secrets=[
        modal.Secret.from_name("r2-storage-config"),
        modal.Secret.from_name("agnes-key"),
    ]
)
def inspect_secrets():
    import os
    return {
        "R2_ENDPOINT": os.getenv("R2_ENDPOINT", "NOT_SET"),
        "R2_ACCESS_KEY_ID": "SET" if os.getenv("R2_ACCESS_KEY_ID") else "NOT_SET",
        "R2_SECRET_ACCESS_KEY": "SET" if os.getenv("R2_SECRET_ACCESS_KEY") else "NOT_SET",
        "R2_BUCKET": os.getenv("R2_BUCKET", "NOT_SET"),
        "R2_PUBLIC_DOMAIN": os.getenv("R2_PUBLIC_DOMAIN", "NOT_SET"),
        "AGNES_API_KEY": "SET" if os.getenv("AGNES_API_KEY") else "NOT_SET",
    }

@app.local_entrypoint()
def main():
    result = inspect_secrets.remote()
    print("SECRET INSPECTION RESULT:")
    for k, v in result.items():
        print(f"  {k}: {v}")