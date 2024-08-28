import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool


@tool
def list_s3_buckets_with_sizes_and_counts() -> str:
    """
    List all S3 buckets in the AWS account along with their sizes in KB and the number of objects in each bucket.

    Returns:
        str: A CSV string containing bucket names, sizes in KB, and object counts, or an error message if an exception occurs.
    """
    try:
        s3 = boto3.client("s3")
        buckets = s3.list_buckets()["Buckets"]
        result = "Bucket Name,Size (KB),Object Count\n"
        for bucket in buckets:
            bucket_name = bucket["Name"]
            size_kb = 0
            object_count = 0
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        size_kb += obj["Size"] / 1024
                        object_count += 1
            result += f"{bucket_name},{size_kb},{object_count}\n"
        return result
    except (BotoCoreError, ClientError) as error:
        return str(error)
