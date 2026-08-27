import modal
import os

image = modal.Image.debian_slim().pip_install("boto3")

app = modal.App("create-r2-bucket", image=image)

@app.function(
    secrets=[modal.Secret.from_name("r2-storage-config")]
)
def create_bucket():
    import boto3
    import os
    
    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    print(f"Endpoint: {endpoint}")
    print(f"Access Key: {access_key[:10]}..." if access_key else "NOT SET")
    
    # Extract account ID from endpoint
    # https://b8743fc421303345b81bce87d3b10742.r2.cloudflarestorage.com
    # Account ID is the prefix before .r2.cloudflarestorage.com
    account_id = endpoint.split("://")[1].split(".")[0] if endpoint else None
    print(f"Account ID: {account_id}")
    
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    
    bucket_name = "music-assets"
    
    try:
        # Check if bucket exists
        client.head_bucket(Bucket=bucket_name)
        print(f"Bucket '{bucket_name}' already exists")
        return {"status": "exists", "bucket": bucket_name}
    except client.exceptions.ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            print(f"Bucket '{bucket_name}' does not exist, creating...")
            client.create_bucket(Bucket=bucket_name)
            print(f"Bucket '{bucket_name}' created successfully")
            return {"status": "created", "bucket": bucket_name}
        else:
            raise

@app.local_entrypoint()
def main():
    result = create_bucket.remote()
    print("RESULT:", result)

if __name__ == "__main__":
    main()