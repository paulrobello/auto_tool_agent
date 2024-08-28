import boto3
from langchain_core.tools import tool


@tool
def list_s3_buckets_and_storage_class(region: str = "None"):
    """
    List all S3 buckets and their storage classes optionally filtering by region.

    Args:
        region (str): Region to filter buckets by. Use "None" to list all buckets.

    Returns:
        dict: A dictionary containing the list of S3 buckets with their storage classes or an error message.
    """
    try:
        session = boto3.Session()
        s3 = session.client("s3")

        buckets_response = s3.list_buckets()
        buckets = buckets_response["Buckets"]

        bucket_info = {}
        for bucket in buckets:
            bucket_name = bucket["Name"]
            bucket_location = s3.get_bucket_location(Bucket=bucket_name)[
                "LocationConstraint"
            ]

            # Handle the us-east-1 region case
            if bucket_location is None:
                bucket_location = "us-east-1"

            # Filter by region if specified
            if region in ["None", None, bucket_location]:
                # Get the storage class for the bucket (by checking a sample object's storage class, if exists)
                storage_class = "STANDARD"  # Default assumption
                try:
                    objects = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    if "Contents" in objects and objects["Contents"]:
                        first_object = objects["Contents"][0]
                        storage_class = first_object.get("StorageClass", "STANDARD")
                except Exception as e:
                    storage_class = f"Error retrieving storage class: {str(e)}"

                bucket_info[bucket_name] = {
                    "Location": bucket_location,
                    "StorageClass": storage_class,
                }

        return bucket_info
    except Exception as error:
        return f"Error: {error}"
