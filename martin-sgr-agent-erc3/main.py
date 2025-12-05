import os
import textwrap
from agent import run_agent
from erc3 import ERC3
from openai import OpenAI
from dotenv import load_dotenv

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
# core.submit_session("ssn-42QmyqTRz6TVeZ3fPLTWQZ")
# exit(0)

# !!! Needs to be a model that supports structured output
MODEL_ID = 'x-ai/grok-4.1-fast'
# MODEL_ID = 'openai/gpt-5-mini'

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
    'broken_system',
    'nonlead_pauses_project',
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

    try:
        run_agent(client, MODEL_ID, core, task)
    except Exception as e:
        print(e)
    # finally:
    #     exit(0)
    result = core.complete_task(task)
    if result.eval:
        explain = textwrap.indent(result.eval.logs, "  ")
        print(f"\nSCORE: {result.eval.score}\n{explain}\n")

# core.submit_session(res.session_id)











