import modal

image = modal.Image.debian_slim().pip_install("requests")

app = modal.App("inspect-token", image=image)

@app.function(secrets=[modal.Secret.from_name("r2-storage-config")])
def get_token():
    import os
    return {
        'MODAL_AUTH_TOKEN': os.getenv('MODAL_AUTH_TOKEN', 'NOT_SET'),
        'MODAL_TOKEN': os.getenv('MODAL_TOKEN', 'NOT_SET'),
    }

@app.local_entrypoint()
def main():
    result = get_token.remote()
    print("TOKEN INSPECTION RESULT:")
    for k, v in result.items():
        print(f"  {k}: {v}")