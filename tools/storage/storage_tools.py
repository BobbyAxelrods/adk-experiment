from google.cloud import storage
from typing import Dict, Any, Optional

def create_gcs_bucket(tool_context: Any, bucket_name: str, location: str) -> Dict[str, Any]:
    """
    Creates a Google Cloud Storage bucket if it doesn't exist.
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            bucket.create(location=location)
            return {
                "status": "success", 
                "message": f"Bucket {bucket_name} created in {location}",
                "bucket_name": bucket_name
            }
        return {
            "status": "success", 
            "message": f"Bucket {bucket_name} already exists",
            "bucket_name": bucket_name
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Failed to create bucket: {str(e)}"
        }

def list_blobs(bucket_name: str, prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    Lists blobs in a Google Cloud Storage bucket.
    """
    try:
        storage_client = storage.Client()
        blobs = storage_client.list_blobs(bucket_name, prefix=prefix)
        blob_list = [blob.name for blob in blobs]
        return {
            "status": "success", 
            "blobs": blob_list,
            "count": len(blob_list),
            "message": f"Found {len(blob_list)} blobs in {bucket_name}"
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Failed to list blobs: {str(e)}"
        }
