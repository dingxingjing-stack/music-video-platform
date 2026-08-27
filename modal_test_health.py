import modal

image = modal.Image.debian_slim(python_version="3.10").pip_install("fastapi")

app = modal.App("test-health-endpoint", image=image)

@app.function()
@modal.fastapi_endpoint(method="GET")
def health():
    return {"status": "ok", "model": "test"}

if __name__ == "__main__":
    modal.run(app.health)