# AI agent that can create its own tools **LangGraph Edition**

# Work in progress. May be broken at any time.

## Overview
This agent uses a multistep process to create its own tools and use them to answer questions.

## Prerequisites
* gnu compatible Make
* python 3.11+
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

### Dev mode uses uv to run the agent
```bash
uv run python -m auto_tool_agent "list all lambda functions in region us-east-1"
```

```bash
uv run python -m auto_tool_agent -f csv "list all lambda functions in region us-east-1"
```

### Normal run examples

Output CSV format to file data.csv using query of s3 buckets and their storage classes:
```bash
auto_tool_agent --format csv --output data.csv "list all s3 buckets and their storage class"
```

Output Markdown format to file data.md using query of top 5 hacker news articles:
```bash
auto_tool_agent.exe -f markdown -o data.markdown "fetch me the top 5 articles from hacker news"
```

## Output format examples dev mode
You can specify any of the supported output formats enhance the system prompt for better output formatting.  
### Markdown
```bash
uv run python -m auto_tool_agent -f markdown -o data.md "list all s3 buckets in region us-east-1"
```

### CSV
```bash
uv run python -m auto_tool_agent -f csv -o data.csv "list all s3 buckets in region us-east-1"
```

### JSON
```bash
uv run python -m auto_tool_agent -f json -o data.json 'list all s3 buckets in region us-east-1. Use the following json schema [{"bucket_name": "string", "region": "string"}]'
```

### Text
```bash
uv run python -m auto_tool_agent -f  text -o data.txt "list all s3 buckets in region us-east-1."
```

## Folders
* ~/.config/auto_tool_agent/sandbox - sandbox folder where the agent will write project files
* ~/.config/auto_tool_agent/sandbox/src/sandbox - folder where the agent will write its tools

## Agent Logic


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
