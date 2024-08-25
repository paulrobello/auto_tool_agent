from typing import Dict, Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool


@tool
def list_s3_buckets_in_regions(regions: list) -> Dict[str, Any]:
    """
    List all S3 buckets in the specified AWS regions.

    Args:
        regions (list): List of AWS regions to list S3 buckets from.

    Returns:
        dict: A dictionary containing the list of S3 buckets with their regions or an error message.
    """
    result = {}
    for region in regions:
        try:
            s3_client = boto3.client("s3", region_name=region)
            paginator = s3_client.get_paginator("list_buckets")
            response_iterator = paginator.paginate()
            buckets = []
            for page in response_iterator:
                for bucket in page.get("Buckets", []):
                    buckets.append(bucket["Name"])
            result[region] = buckets
        except Exception as error:
            result[region] = str(error)
    return result
