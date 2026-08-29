import modal

app = modal.App("avireon-cpu-test")

image = modal.Image.debian_slim(python_version="3.12")

@app.function(image=image, timeout=60)
def hello():
    return "CPU_OK"
