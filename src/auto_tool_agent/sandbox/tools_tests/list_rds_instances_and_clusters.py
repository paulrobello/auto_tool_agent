import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool


@tool
def list_rds_instances_and_clusters(region: str) -> dict:
    """
    List all RDS instances and clusters in the specified AWS region.
    Args:
        region (str): The AWS region to list RDS instances and clusters from.
    Returns:
        dict: A dictionary containing the list of RDS instances and clusters with their types and versions or an error message.
    """
    try:
        rds_client = boto3.client("rds", region_name=region)

        instance_paginator = rds_client.get_paginator("describe_db_instances")
        cluster_paginator = rds_client.get_paginator("describe_db_clusters")

        instance_list = []
        for page in instance_paginator.paginate():
            for instance in page["DBInstances"]:
                instance_list.append(
                    {
                        "DBInstanceIdentifier": instance["DBInstanceIdentifier"],
                        "DBInstanceClass": instance["DBInstanceClass"],
                        "Engine": instance["Engine"],
                        "EngineVersion": instance["EngineVersion"],
                    }
                )

        cluster_list = []
        for page in cluster_paginator.paginate():
            for cluster in page["DBClusters"]:
                cluster_list.append(
                    {
                        "DBClusterIdentifier": cluster["DBClusterIdentifier"],
                        "Engine": cluster["Engine"],
                        "EngineVersion": cluster["EngineVersion"],
                    }
                )

        return {"DBInstances": instance_list, "DBClusters": cluster_list}
    except Exception as error:
        return {"error": str(error)}
