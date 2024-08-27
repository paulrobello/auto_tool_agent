"""AI TOOLS"""

from __future__ import annotations

import os
from typing import Union, Literal
import datetime

import docker
import docker.types
import psycopg2
import simplejson as json

from langchain_core.tools import tool

from auto_tool_agent.session import session
from auto_tool_agent.sandboxing import (
    create_session_folder,
    read_env_file,
)
from auto_tool_agent.tool_funcs import google_search


@tool()
def write_file(data: str, filename: str, append: bool) -> Union[str, Literal[False]]:
    """
    Create or append file on disk

    Args:
        data (str): The data to be written to the file.
        filename (str): The file name to be written.
        append (bool): Whether to append to the file or overwrite it.

    Returns:
        Union[str, False]: The file name of the written file or False if an error occurred.
    """

    if not create_session_folder():
        return False
    filename = os.path.basename(filename)
    mode = "a" if append else "w"
    with open(
        os.path.join(session.opts.sandbox_dir, session.id, filename),
        mode,
        encoding="utf-8",
    ) as f:
        f.write(data)
    return filename


@tool
def read_file(filename: str) -> Union[dict[str, str], Literal[False]]:
    """
    Read a file from disk

    Args:
        filename (str): The file name to read

    Returns:
        Dict[str,str]: Containing keys for filename and data or False if an error occurred.
    """
    try:
        if not create_session_folder():
            return False

        filename = os.path.basename(filename)
        file_path = os.path.join(session.opts.sandbox_dir, session.id, filename)
        if not os.path.exists(file_path):
            return False
        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read()
        return {"filename": filename, "data": data}
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False


@tool
def list_files(
    ignored: str,  # pylint: disable=unused-argument
) -> Union[list[str], Literal[False]]:
    """
    List files in the output directory

    Args:
        ignored (str): Ignored

    Returns:
        List[str]: List of file names or False if an error occurred.
    """
    try:
        if not create_session_folder():
            return False
        files = os.listdir(os.path.join(session.opts.sandbox_dir, session.id))
        return files
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False


@tool
def rename_file(old_filename: str, new_filename: str) -> Union[str, Literal[False]]:
    """
    Rename a file in the output directory.
    This tool will not overwrite existing files.

    Args:
        old_filename (str): The current name of the file.
        new_filename (str): The new name of the file.

    Returns:
        str: The new name of the file or False if an error occurred.
    """
    try:
        if not create_session_folder():
            return False

        old_filename = os.path.basename(old_filename)
        new_filename = os.path.basename(new_filename)
        file_path = os.path.join(session.opts.sandbox_dir, session.id, old_filename)
        new_file_path = os.path.join(session.opts.sandbox_dir, session.id, new_filename)
        if not os.path.exists(file_path):
            return False
        if os.path.exists(new_file_path):
            return False
        os.rename(file_path, new_file_path)
        return new_filename
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False


@tool
# pylint: disable=too-many-locals
def introspect_database(
    db_name: str,
) -> Union[str, Literal[False]]:
    """
    Introspect a postgres database and return json schema

    Args:
        db_name (str): The database name to introspect.

    Returns:
        str: The json schema of the database or False if database does not exist.
    """

    try:
        db_user = os.environ["DB_USER"]
        db_password = os.environ["DB_PASSWORD"]
        # db_name = os.environ['DB_NAME']
        db_host = os.environ.get("DB_HOST", "127.0.0.1")

        # Connect to the database
        conn = psycopg2.connect(
            host=db_host, database=db_name, user=db_user, password=db_password
        )

        # Create a cursor object
        cur = conn.cursor()

        # Get a list of all tables in the database
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables = [table[0] for table in cur.fetchall()]

        # Initialize an empty dictionary to store the schema
        schema = {"tables": {}, "relationships": []}

        # Loop through each table and get its schema
        for table in tables:
            cur.execute(
                f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = '{table}'"
            )
            columns = cur.fetchall()

            # Initialize an empty list to store the column definitions
            column_definitions = []

            # Loop through each column and create a definition
            for column in columns:
                column_name, data_type, is_nullable = column
                column_definition = {
                    "name": column_name,
                    "type": data_type,
                    "nullable": is_nullable == "YES",
                }
                column_definitions.append(column_definition)

            # Add the table and its column definitions to the schema
            schema["tables"][table] = column_definitions

        # Get a list of all foreign key constraints
        cur.execute(
            """
            SELECT
                tc.table_name, kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM
                information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY';
        """
        )
        foreign_keys = cur.fetchall()

        # Loop through each foreign key and create a relationship object
        for foreign_key in foreign_keys:
            table_name, column_name, foreign_table_name, foreign_column_name = (
                foreign_key
            )
            relationship = {
                "name": f"{table_name}_{column_name}_fkey",
                "type": "one-to-many",
                "parent_table": foreign_table_name,
                "parent_columns": [foreign_column_name],
                "child_table": table_name,
                "child_columns": [column_name],
            }
            schema["relationships"].append(relationship)

        # Close the database connection
        cur.close()
        conn.close()

        # Convert the schema dictionary to JSON and print it
        json_schema = json.dumps(schema, indent=4)
        print(json_schema)
        return json_schema
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False


@tool
def search_web(query: str) -> Union[str, Literal[False]]:
    """
    Search the web using google search

    Args:
        query (str): The search query

    Returns:
        Union[str, False]: The search results in json format or False if an error occurred
    """

    results = google_search(query)
    if not results:
        return False
    return json.dumps(results["items"])


@tool
def get_now(query: str) -> str:  # pylint: disable=unused-argument
    """
    Get current date and time

    Args:
        query (str): ignored

    Returns:
        str: The current date and time
    """

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


@tool
def execute_script(
    script_filename: str, requirements_filename: str | None
) -> Union[dict[str, str | None], Literal[False]]:
    """
    Execute a python script in a docker container

    Args:
        script_filename (str): The name of the file to execute
        requirements_filename (str | None): The name of the requirements file to install before executing the script

    Returns:
        Union[dict[str, str | None], False]: pip_output, run_output, exit_code of the script or False if an error occurs
    """

    try:
        env = read_env_file("../.env") | read_env_file(".env")

        script_filename = os.path.basename(script_filename)

        client = docker.DockerClient(base_url="tcp://127.0.0.1:2375", tls=False)
        container = client.containers.run(
            "python:3.11",
            "tail -f /dev/null",
            detach=True,
            environment=env,
            mounts=[
                docker.types.Mount(
                    target="/workspace",
                    source=os.path.abspath(
                        os.path.join(session.opts.sandbox_dir, session.id)
                    ),
                    type="bind",
                )
            ],
        )
        # print(container.logs())
        pip_output: str = ""
        if requirements_filename:
            requirements_filename = os.path.basename(requirements_filename)
            (exit_code, output) = container.exec_run(
                f"pip install -r {requirements_filename}", workdir="/workspace"
            )
            pip_output = output.decode("utf-8")
            with open(
                os.path.join(
                    session.opts.sandbox_dir,
                    session.id,
                    f"{script_filename}.pip-output.txt",
                ),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(pip_output)
            if exit_code != 0:
                print(f"Error: {pip_output}")
                return {
                    "pip_output": pip_output,
                    "run_output": None,
                    "exit_code": exit_code,
                }
            pip_output = "Success"
        (exit_code, output) = container.exec_run(
            f"python {script_filename}", workdir="/workspace"
        )
        run_output: str = output.decode("utf-8")
        with open(
            os.path.join(
                session.opts.sandbox_dir,
                session.id,
                f"{script_filename}.run-output.txt",
            ),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(run_output)

        # print(f"Exit code: {exit_code}")
        # print(output.decode("utf-8"))
        # print(container.logs())
        container.stop()
        container.remove()
        return {
            "pip_output": pip_output,
            "run_output": run_output,
            "exit_code": exit_code,
        }
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}")
        return False
