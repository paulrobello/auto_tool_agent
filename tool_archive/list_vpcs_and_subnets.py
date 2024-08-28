from boto3 import client
from langchain_core.tools import tool


@tool
def list_vpcs_and_subnets(region: str) -> str | dict:
    """
    List all VPCs and their subnets in the specified AWS region.

    Args:
        region (str): The AWS region to list VPCs and subnets from.

    Returns:
        dict: A dictionary containing the list of VPCs and their subnets, or an error message.
    """
    try:
        ec2_client = client("ec2", region_name=region)
        vpcs = {}

        # List VPCs
        vpc_response = ec2_client.describe_vpcs()
        for vpc in vpc_response["Vpcs"]:
            vpc_id = vpc["VpcId"]
            vpc_name = next(
                (tag["Value"] for tag in vpc["Tags"] if tag["Key"] == "Name"), vpc_id
            )
            vpcs[vpc_name] = {"VpcId": vpc_id, "Subnets": []}

        # List subnets for each VPC
        subnet_response = ec2_client.describe_subnets()
        for subnet in subnet_response["Subnets"]:
            vpc_id = subnet["VpcId"]
            subnet_id = subnet["SubnetId"]
            subnet_name = next(
                (tag["Value"] for tag in subnet["Tags"] if tag["Key"] == "Name"),
                subnet_id,
            )
            vpcs[
                next(
                    vpc_name
                    for vpc_name, vpc_data in vpcs.items()
                    if vpc_data["VpcId"] == vpc_id
                )
            ]["Subnets"].append(subnet_name)

        return vpcs
    except Exception as error:
        return f"An error occurred: {error}"
