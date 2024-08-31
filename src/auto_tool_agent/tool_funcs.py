"""General TOOLS"""

from __future__ import annotations

import os
from pathlib import Path

from typing import Union, Literal
from urllib.parse import quote
import requests
import docker.types
from docker import DockerClient
from docker.models.containers import Container

from auto_tool_agent.sandboxing import read_env_file


def google_search(query: str) -> Union[dict, Literal[False]]:
    """
    Search the web using google search

    Args:
        query (str): The search query

    Returns:
        Union[dict, False]: The search results or False if an error occurred
    """

    if not os.getenv("GOOGLE_CSE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"):
        return False

    url = f"https://customsearch.googleapis.com/customsearch/v1?c2coff=1&key={os.getenv('GOOGLE_CSE_API_KEY')}&cx={os.getenv('GOOGLE_CSE_ID')}&hl=english&safe=off&num=3&q={quote(query, safe='')}"

    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            return response.json()
        print("Failed to retrieve search results")
        return False
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False


# pylint: disable=too-many-arguments, too-many-locals
def start_docker_container(
    image: str,
    *,
    container_name: str,
    command: str | None = None,
    env: dict | None = None,
    ports: dict | None = None,
    network_name: str | None = None,
    mounts: list[docker.types.Mount] | None = None,
    re_create: bool = False,
    remove: bool = False,
    background: bool = True,
) -> Union[bool, str]:
    """
    Start a docker container if it exists, otherwise create it

    Args:
        image (str): The base image to use
        container_name (str): The name of the container
        command (str | None): The command line to run. Defaults to None
        env (dict | None): The environment variables to use. Defaults to None
        ports (dict | None): The ports to expose. Defaults to None
        network_name (str | None): The network to use. Defaults to None
        mounts (List[docker.types.Mount]): The mounts to use. Example: [docker.types.Mount(target="/workspace", source=f"{os.getcwd()}/output/{session_id}", type="bind")]
        re_create (bool): Whether to recreate the container if it exists. Defaults to False
        remove (bool): Whether to remove the container after execution. Defaults to False
        background (bool): Whether to run the container in the background. Defaults to True

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        if not env:
            env = {}
        env = read_env_file(Path("../.env")) | read_env_file(Path(".env")) | env

        client: DockerClient = docker.DockerClient(
            base_url="tcp://127.0.0.1:2375", tls=False
        )
        if network_name:
            try:
                networks = client.networks.list(names=[network_name])
                if len(networks) > 0:
                    # network = networks[0]
                    print(f"Network {network_name} exists.")
                else:
                    # network = client.networks.create(network_name, driver="bridge")
                    print(f"Network {network_name} created")
            except Exception as e:  # pylint: disable=broad-except
                print(f"Error: {e}")

        # container = client.containers.list(all=True, filters={"name": container_name})
        try:
            container = client.containers.get(container_name)
            print(f"Container {container_name} exists.")
            if re_create:
                print(f"Recreating container {container_name}")
                container.remove(force=True)
            else:
                if container.status == "running":
                    print(f"Container {container_name} is already running.")
                    return True
                print(f"Starting container {container_name}")
                container.start()
                return True
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error1: {e}")

        print(f"Container {container_name} does not exist. Creating...")
        if background:
            container: Container = client.containers.run(
                image,
                command,
                name=container_name,
                ports=ports,
                detach=background,
                environment=env,
                remove=remove,
                network=network_name,
                mounts=mounts,
            )
            print(container.status)
            return True

        logs: bytes = client.containers.run(
            image,
            command,
            name=container_name,
            ports=ports,
            detach=background,
            environment=env,
            remove=remove,
            network=network_name,
            mounts=mounts,
        )
        return logs.decode("utf-8").strip()
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False
