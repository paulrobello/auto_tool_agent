import boto3
from langchain_core.tools import tool


@tool
def list_s3_buckets_and_storage_class(ignored: str):
    """
    List all S3 buckets and their storage classes in a specific region.

    Args:
        ignored (str): Ignored

    Returns:
        dict: A dictionary containing the list of S3 buckets with their storage classes or an error message.
    """
    try:
        # Use the default AWS credentials
        session = boto3.Session()
        s3 = session.client("s3")

        # Use pagination to retrieve all buckets
        buckets = []
        paginator = s3.get_paginator("list_buckets")
        for page in paginator.paginate():
            buckets.extend(page["Buckets"])

        bucket_info = {}
        for bucket in buckets:
            bucket_name = bucket["Name"]
            storage_class = s3.get_bucket_location(Bucket=bucket_name)[
                "LocationConstraint"
            ]
            bucket_info[bucket_name] = storage_class
        return bucket_info
    except Exception as error:
        return f"Error: {error}"
