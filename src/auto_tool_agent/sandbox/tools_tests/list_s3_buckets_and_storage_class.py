import logging
from typing import Optional

import boto3
from langchain_core.tools import tool

@tool
def list_s3_buckets_and_storage_class(region: Optional[str] = None):
    """
    List all S3 buckets and their storage classes in a specific region.

    Args:
        region Optional(str): The AWS region to list S3 buckets from. Use None for all.

    Returns:
        dict: A dictionary containing the list of S3 buckets with their storage classes or an error message.
    """
    try:
        log = logging.getLogger("[orange]tool[/orange]")
        s3 = boto3.client('s3', region_name=region)
        response = s3.list_buckets()
        result = []
        for bucket in response['Buckets']:
            bucket_location = s3.get_bucket_location(Bucket=bucket['Name'])['LocationConstraint']
            log.info(f"Bucket: {bucket['Name']}, Location: {bucket_location}")

            if bucket_location == region:
                paginator = s3.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket['Name']):
                    for obj in page.get('Contents', []):
                        storage_class = obj.get('StorageClass', 'N/A')
                        result.append({'bucket_name': bucket['Name'], 'storage_class': storage_class, 'region': region})
        return result
    except Exception as error:
        return str(error)
