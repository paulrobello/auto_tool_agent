# AI agent that can create its own tools

## Overview
The agent is currently setup to use a system prompt geared for AWS.

## Prerequisites
* gnu compatible Make
* python 3.10+
* uv

## Installation
The following can be used to install and update the dependencies.
```bash
make depsupdate
````

## Environment
You must create a .env file with the need values.  
The project default to OpenAI but can be easily changed to other providers as needed.  
Depending on the features and providers you use fill in the vars as needed.
```bash
# AI Providers
OPENAI_API_KEY=
OPENAI_MODEL_NAME=gpt-4
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GROQ_API_KEY=
PPLX_API_KEY=
HF_TOKEN=
# Search providers
SERPER_API_KEY=
TAVILY_API_KEY=
JINA_API_KEY=
GOOGLE_CSE_ID=
GOOGLE_CSE_API_KEY=

# Other ai tools
LANGFLOW_API_KEY=

### Tracing (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=auto_tool_agent
```

## Usage
Argument help:
```bash
make app_help
```
If using for AWS you must assume the role you want to use prior to running the agent.

Use ARG1, ARG2... env vars to pass arguments to the agent
```bash
ARG1="list all lambda functions in region us-east-1" make run
```

```bash
ARG1="list all s3 buckets in region us-east-1" make run
```

You can also request the agent update or add features to existing tools:
```bash
ARG1="add boto3 paginator to tool list_s3_buckets" make run
```

## Agent Logic

### System prompt
The agent has access to system prompts in the `src/auto_tool_agent/system_prompts folder`.  
You can change the default system prompt with the --system_prompt or -s param.  
The default system prompt is aws.md which is tuned for AWS.

### Tool folders
The agent has an always available set of tools to allow it to list, read and write files in the tools_tests folder.  
The tools_tests folder is the only folder that the agent has access to.

### Iterations
Each time the agent needs to create or update a tool it will start a new iteration.
The maximum number of iterations defaults to 5 but can be changed with the --max_iterations or -m param.

Example 1:  
* 1st iteration: Agent looks at user request and decides it needs to create a tool.
* 2nd iteration: Agent uses the tool to generate an answer.

Example 2:
* 1st iteration: Agent looks at user request and decides has all tools it needs and generates an answer.

Example 3:
* 1st iteration: Agent looks at user request and decides it needs to create a tool.
* 2nd iteration: Agent uses the tool but gets an error, looks looks at the broken tool and fixes it.
* 3rd iteration: Agent uses the tool to generate an answer.


## Running in the Generic Development Container (GDC)
The [GDC](https://github.com/devxpod/GDC/) is a project I created years go to create a highly configurable IDE agnostic rapid development container.  
Because the agent creates its own tools and those tools execute code locally where you are running the agent you may want some extra security / sandboxing.
While using the GDC is not required to run the agent in a container it has many quality of life benefits for any developer.  
Follow the GDC installation instructions then run the following command from the repository root:
```bash
run-dev-container.sh
```
Then in a separate terminal run:
```bash
docker exec -it auto_tool_agent-dev-1 bash -l
```
This will drop you at a prompt in the repository root inside the container.  
Now you can run the agent in the normal way without worry that any code it generates causing any damage to your system.
