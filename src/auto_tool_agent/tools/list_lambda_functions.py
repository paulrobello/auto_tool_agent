from boto3 import client
from langchain_core.tools import tool


@tool
def list_lambda_functions(region: str) -> str | list[dict]:
    """
    List all AWS Lambda functions in a region.

    Args:
        region (str): The AWS region to list Lambda functions from.

    Returns:
        list: A list of Lambda function names or an error message.
    """
    try:
        lambda_client = client("lambda", region_name=region)
        lambda_functions = []
        paginator = lambda_client.get_paginator("list_functions")
        for page in paginator.paginate():
            for function in page["Functions"]:
                lambda_functions.append(function["FunctionName"])
        return lambda_functions
    except Exception as error:
        return f"An error occurred: {error}"
