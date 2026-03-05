from google.cloud import storage
from typing import Dict, Any, Optional
from google.adk.tools import FunctionTool

def create_gcs_bucket(bucket_name: str, location: str) -> Dict[str, Any]:
    """
    Create GCS bucket.
    
    Creates a Google Cloud Storage bucket if it doesn't exist.
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            bucket.create(location=location)
            return {"status": "success", "message": f"Bucket {bucket_name} created in {location}"}
        return {"status": "success", "message": f"Bucket {bucket_name} already exists"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to create bucket: {str(e)}"}

def list_blobs(bucket_name: str, prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    List blobs in GCS bucket.
    
    Lists blobs in a Google Cloud Storage bucket.
    """
    try:
        storage_client = storage.Client()
        blobs = storage_client.list_blobs(bucket_name, prefix=prefix)
        blob_list = [blob.name for blob in blobs]
        return {"status": "success", "blobs": blob_list, "count": len(blob_list)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ADK Tool Definitions
create_gcs_bucket = FunctionTool(func=create_gcs_bucket)
list_blobs = FunctionTool(func=list_blobs)
