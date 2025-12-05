import time
from typing import Annotated, List, Union
from annotated_types import MaxLen, MinLen
from mlflow.entities import SpanType
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from erc3 import erc3 as dev, ApiException, TaskInfo, ERC3
from current_user_agent import CurrentUserQuestion, CurrentUserAgent
from error_handling_agent import ErrorHandlingAgent, create_error_response
import mlflow

class NextStep(BaseModel):
    current_state: str
    # we'll use only the first step, discarding all the rest.
    plan_remaining_steps_brief: Annotated[List[str], MinLen(1), MaxLen(5)] =  Field(..., description="explain your thoughts on how to accomplish - what steps to execute")
    # now let's continue the cascade and check with LLM if the task is done
    task_completed: bool
    # Routing to one of the tools to execute the first remaining step
    # if task is completed, model will pick ReportTaskCompletion
    function: Union[
        CurrentUserQuestion,
        dev.Req_ProvideAgentResponse,
        dev.Req_ListProjects,
        dev.Req_ListEmployees,
        dev.Req_ListCustomers,
        dev.Req_GetCustomer,
        dev.Req_GetEmployee,
        dev.Req_GetProject,
        dev.Req_GetTimeEntry,
        dev.Req_SearchProjects,
        dev.Req_SearchEmployees,
        dev.Req_LogTimeEntry,
        dev.Req_SearchTimeEntries,
        dev.Req_SearchCustomers,
        dev.Req_UpdateTimeEntry,
        dev.Req_UpdateProjectTeam,
        dev.Req_UpdateProjectStatus,
        dev.Req_UpdateEmployeeInfo,
        dev.Req_TimeSummaryByProject,
        dev.Req_TimeSummaryByEmployee,
    ] = Field(..., description="execute first remaining step")



CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_BLUE = "\x1B[34m"
CLI_CLR = "\x1B[0m"

@mlflow.trace(span_type=SpanType.AGENT)
def run_agent(client: OpenAI, model: str, api: ERC3, task: TaskInfo):

    store_api = api.get_erc_client(task)
    about = store_api.who_am_i()

    rulebook = store_api.load_wiki("rulebook.md")

    current_user_agent = CurrentUserAgent(client, model, store_api)
    error_handler = ErrorHandlingAgent(client, model)

    system_prompt = f"""
You are a business assistant helping customers of Aetherion.

When interacting with Aetherion's internal systems, always operate strictly within the user's access level 
(Executives have broad access, project leads can write with the projects they lead, team members can read). 
For guests (public access, no user account) respond exclusively with public-safe data, 
refuse sensitive queries politely, and never reveal internal details or identities. 
Successful responses must always include a clear outcome status and explicit entity links.

To confirm project access - get or find project (and get after finding)
When updating entry - fill all fields to keep with old values from being erased
When task is done or can't be done - Req_ProvideAgentResponse.

# Pitfalls:
- "limit" and "offset" DO NOT set negative values, this is an error.
- If a request returns an error, that resource cannot be found, DO NOT retry it again.
- If you fail with a non "ok" outcome, DO NOT provide any links.
- When asked to perform a certain action, DO first check if the action is available and allowed for the user.

<file "rulebook.md">
{rulebook.content}
</file>

# Current user info:
{about.model_dump_json()}
"""
    if about.current_user:
        usr = store_api.get_employee(about.current_user)
        system_prompt += f"\n{usr.model_dump_json()}"
    else:
        system_prompt += f"\nUser specified in the task not found! Operating with public access only."

    # log will contain conversation context for the agent within task
    log = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task.task_text},
    ]

    # let's limit number of reasoning steps by 20, just to be safe
    for i in range(20):
        step = f"step_{i + 1}"
        print(f"Next {step}... ", end="")

        started = time.time()

        try:
            completion = client.beta.chat.completions.parse(
                model=model,
                response_format=NextStep,
                messages=log,
                max_completion_tokens=16384,
            )
        except ValidationError as e:
            # print stack trace
            print(f"{CLI_RED}ERR: Exception during LLM call: {e}{CLI_CLR}")
            break

        api.log_llm(
            task_id=task.task_id,
            model=model, # must match slug from OpenRouter
            duration_sec=time.time() - started,
            usage=completion.usage,
        )

        job = completion.choices[0].message.parsed

        # print next sep for debugging
        print(job.plan_remaining_steps_brief[0], f"\n  {job.function}")

        log.append({
            "role": "assistant",
            "content": job.plan_remaining_steps_brief[0],
            "tool_calls": [{
                "type": "function",
                "id": step,
                "function": {
                    "name": job.function.__class__.__name__,
                    "arguments": job.function.model_dump_json(),
                }}]
        })

        # now execute the tool by dispatching command to our handler
        if isinstance(job.function, CurrentUserQuestion):
            current_user_agent.gather_init_data()
            txt = current_user_agent.ask_question(job.function.question)
            print(f"{CLI_GREEN}OUT{CLI_CLR}: {txt}")
        else:
            try:
                @mlflow.trace(span_type=SpanType.TOOL)
                def tool_call(function):
                    return store_api.dispatch(function)
                result = tool_call(job.function)
                txt = result.model_dump_json(exclude_none=True, exclude_unset=True)
                print(f"{CLI_GREEN}OUT{CLI_CLR}: {txt}")

                # and now we add results back to the conversation history, so that agent
                # we'll be able to act on the results in the next reasoning step.
                log.append({
                    "role": "tool",
                    "tool_call_id": step,
                    "function": job.function.__class__.__name__,
                    "output": txt,
                })
            except ApiException as e:
                # Analyze the error using error handling agent
                context = f"Executing {job.function.__class__.__name__}"
                analysis = error_handler.analyze_error(e, context)

                # Create final error response and exit loop
                error_response = create_error_response(analysis)
                print(f"{CLI_BLUE}error agent {error_response['outcome']}{CLI_CLR}. Summary:\n{error_response['message']}")

                # Add error response to log as if it was the agent's decision
                log.append({
                    "role": "tool",
                    "tool_call_id": step,
                    "function": "error_handling",
                    "content": analysis.model_dump_json()
                })

            # if SGR wants to finish, then quit loop
        if isinstance(job.function, dev.Req_ProvideAgentResponse):
            print(f"{CLI_BLUE}agent {job.function.outcome}{CLI_CLR}. Summary:\n{job.function.message}")

            for link in job.function.links:
                print(f"  - link {link.kind}: {link.id}")

            break
