from typing import List, Dict, Any, Union
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool


@tool
def list_ec2_instances(region: str) -> Union[str, List[Dict[str, Any]]]:
    """
    List all EC2 instances in the specified AWS region.

    Args:
        region (str): The AWS region to list EC2 instances from.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing EC2 instance details or an error message.
    """
    try:
        ec2_client = boto3.client("ec2", region_name=region)
        paginator = ec2_client.get_paginator("describe_instances")
        response_iterator = paginator.paginate()

        instances = []
        for page in response_iterator:
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instances.append(instance)

        return instances
    except Exception as error:
        return str(error)
