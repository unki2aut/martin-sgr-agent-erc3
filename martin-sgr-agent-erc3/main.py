import json
import os
import textwrap
from agent import run_agent
from erc3 import ERC3
from openai import OpenAI
from dotenv import load_dotenv
import mlflow

from api_utils import list_projects

mlflow.set_tracking_uri("http://localhost:5123")
mlflow.openai.autolog()

from current_user_agent import CurrentUserAgent
from dump_wiki import dump_wiki

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is not set")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

core = ERC3(key=os.getenv("EC3_API_KEY", ""))

# !!! Needs to be a model that supports structured output
MODEL_ID = 'x-ai/grok-4.1-fast'
# MODEL_ID = 'openai/gpt-4.1-mini'
# MODEL_ID = 'openai/gpt-4o-mini'

# Start session with metadata
res = core.start_session(
    benchmark="erc3-dev",
    workspace="my",
    name=f"TAT Team ({MODEL_ID})",
    architecture="NextStep SGR Agent with rulebook and current user sub-agent")

status = core.session_status(res.session_id)
print(f"Session has {len(status.tasks)} tasks")

failed_tasks = [
    # 'not_available_feature',
    # 'broken_system',
    # 'nonlead_pauses_project', project not found
    'add_time_entry_me',
    'add_time_entry_lead',
    'ceo_raises_salary',
]

for task in status.tasks:
    if task.spec_id not in failed_tasks:
        continue

    store_api = core.get_erc_client(task)

    print("="*40)
    print(f"Starting Task: {task.task_id} ({task.spec_id}): {task.task_text}")
    # start the task
    core.start_task(task)

    # projects = list_projects(store_api)
    # print(json.dumps(projects, indent=2))
    # exit(0)

    try:
        mlflow.set_experiment(f"Session: {res.session_id}, Task: {task.spec_id}")
        run_agent(client, MODEL_ID, core, task)
    except Exception as e:
        print(e)

    result = core.complete_task(task)
    if result.eval:
        explain = textwrap.indent(result.eval.logs, "  ")
        print(f"\nSCORE: {result.eval.score}\n{explain}\n")

    # only test one task for now
    exit(0)

# core.submit_session(res.session_id)











