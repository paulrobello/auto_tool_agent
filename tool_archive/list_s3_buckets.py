from typing import List, Union
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool


@tool
def list_s3_buckets() -> Union[List[str], str]:
    """
    List all S3 buckets in the AWS account.

    Returns:
        Union[List[str], str]: A list of bucket names or an error message if an exception occurs.
    """
    try:
        s3 = boto3.client("s3")
        response = s3.list_buckets()
        buckets = [bucket["Name"] for bucket in response["Buckets"]]
        return buckets
    except (BotoCoreError, ClientError) as error:
        return str(error)
