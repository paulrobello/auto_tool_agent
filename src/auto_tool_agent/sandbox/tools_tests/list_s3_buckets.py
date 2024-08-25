from langchain_core.tools import tool
import boto3
from botocore.exceptions import BotoCoreError, ClientError


@tool
def list_s3_buckets(region):
    """
    List all S3 buckets in a specified AWS region.

    Args:
    region (str): The AWS region to list S3 buckets from.

    Returns:
    list: A list of S3 bucket names in the specified AWS region.
    """
    try:
        s3 = boto3.client("s3", region_name=region)
        response = s3.list_buckets()

        buckets = [bucket["Name"] for bucket in response["Buckets"]]

        return buckets

    except Exception as error:
        return str(error)
