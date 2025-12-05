# Architecture Documentation

## Overview

This is a Schema-Guided Reasoning (SGR) agent implementation designed for the ERC3 benchmark platform. The agent automates enterprise API interactions for a fictional AI consulting company (Aetherion Analytics GmbH) by processing natural language tasks and converting them into structured API calls.

## System Architecture

### High-Level Design

The system follows a **NextStep SGR (Schema-Guided Reasoning)** architecture pattern:

```
User Task → Agent Loop → Structured Response → API Call → Result → Next Step
     ↑                                                                    ↓
     └────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Main Entry Point (`main.py`)

**Responsibilities:**
- Initialize ERC3 platform connection
- Configure OpenAI client with OpenRouter API
- Start benchmark sessions
- Iterate through tasks and invoke the agent
- Track results with MLflow for observability

**Key Dependencies:**
- OpenRouter API (for LLM access)
- ERC3 SDK (for benchmark platform integration)
- MLflow (for tracing and logging)

**Flow:**
1. Load environment variables (API keys)
2. Create OpenAI client pointing to OpenRouter
3. Start ERC3 session for specific benchmark (erc3-dev/erc3-test)
4. For each task:
   - Start task tracking
   - Run the agent
   - Complete task and retrieve evaluation score

#### 2. Agent Core (`agent.py`)

**Responsibilities:**
- Implement the main reasoning loop
- Coordinate between LLM and API calls
- Manage conversation history
- Handle structured output parsing

**Architecture Pattern: NextStep SGR**

The agent uses a structured reasoning loop with the following schema:

```python
class NextStep(BaseModel):
    current_state: str                      # Current understanding
    plan_remaining_steps_brief: List[str]   # 1-5 steps planned
    task_completed: bool                     # Completion flag
    function: Union[...]                     # Next API call to execute
```

**Reasoning Loop (20 steps max):**

```
1. Receive task from user
2. Load system context (rulebook, user info)
3. Loop:
   a. LLM generates NextStep (structured output)
   b. Extract first planned step
   c. Execute corresponding function/API call
   d. Add result to conversation history
   e. Check if task completed (Req_ProvideAgentResponse)
   f. Continue or exit
```

**Key Features:**
- Structured output ensures predictable API calls
- Conversation log maintains context across steps
- MLflow tracing for debugging and analysis
- Error handling for API exceptions
- Support for both ERC3 API and internal sub-agents

### Data Flow

#### Task Execution Flow

```
ERC3 Platform
     ↓
  Task Assignment
     ↓
  main.py (session management)
     ↓
  agent.py (reasoning loop)
     ↓
  ┌─────────────────────────────┐
  │  LLM (Structured Output)    │
  │  → NextStep schema          │
  └─────────────────────────────┘
     ↓
  ┌─────────────────────────────────────┐
  │ Function Router                     │
  │  ├─ ERC3 API calls                  │
  │  │   └─ Projects, Employees, etc.   │
  │  └─ CurrentUserAgent                │
  │      └─ User context questions      │
  └─────────────────────────────────────┘
     ↓
  Result → Conversation Log → Next Step
```

#### Information Context

The agent operates with multiple information sources:

1. **System Context** (loaded once per task):
   - `rulebook.md` - Access control and agent behavior rules
   - Current user information via `who_am_i()`
   - Employee details if authenticated

2. **Dynamic Context** (gathered during execution):
   - API responses from previous steps
   - Wiki searches for relevant information
   - User-specific data from CurrentUserAgent

### API Integration

#### ERC3 SDK Integration

The agent interfaces with the ERC3 platform through structured request/response models:

**Available API Operations:**
- **User Context:** `Req_WhoAmI`
- **Listing:** `Req_ListProjects`, `Req_ListEmployees`, `Req_ListCustomers`
- **Retrieval:** `Req_GetCustomer`, `Req_GetEmployee`, `Req_GetProject`, `Req_GetTimeEntry`
- **Search:** `Req_SearchProjects`, `Req_SearchEmployees`, `Req_SearchCustomers`, `Req_SearchTimeEntries`
- **Mutations:** `Req_LogTimeEntry`, `Req_UpdateTimeEntry`, `Req_UpdateProjectTeam`, `Req_UpdateProjectStatus`, `Req_UpdateEmployeeInfo`
- **Analytics:** `Req_TimeSummaryByProject`, `Req_TimeSummaryByEmployee`
- **Response:** `Req_ProvideAgentResponse` (final answer to user)

All requests are dispatched through the `store_api.dispatch()` method with automatic error handling.

#### OpenAI/OpenRouter Integration

**Model Requirements:**
- Must support structured output (JSON schema mode)
- Currently uses: `openai/gpt-4.1-mini` or `x-ai/grok-4.1-fast`

**Structured Output:**
```python
completion = client.beta.chat.completions.parse(
    model=model,
    response_format=NextStep,  # Pydantic schema
    messages=log,
    max_completion_tokens=16384,
)
```

### Security & Access Control

The agent implements role-based access control defined in `rulebook.md`:

**User Levels:**
1. **Executive Leadership** - Broad access to all resources
2. **Senior Specialists/Leads** - City-scoped or responsibility-scoped access
3. **Core Team** - Project-specific access only

**Security Principles:**
- Agent never acts as "root"
- Always operates on behalf of authenticated user
- Denies destructive/irreversible actions without approval
- Protects sensitive data (salaries, personal notes, credentials)
- Public mode provides minimal read-only access

**Response Outcomes:**
- `ok_answer` - Request fulfilled
- `ok_not_found` - Valid request, no results
- `denied_security` - Access denied for policy/permission reasons
- `none_clarification_needed` - Needs more info
- `none_unsupported` - Unsupported request type
- `error_internal` - Internal failure

### Observability

#### MLflow Integration

**Purpose:** Track agent execution for debugging and performance analysis

**Traced Components:**
1. **Agent Execution** - Full reasoning loop (`@mlflow.trace(span_type=SpanType.AGENT)`)
2. **Tool Calls** - Individual API calls (`@mlflow.trace(span_type=SpanType.TOOL)`)
3. **LLM Calls** - OpenAI API calls (via `mlflow.openai.autolog()`)

**Tracking URI:** `http://localhost:5123`

**Logged Metrics:**
- Task ID and specification
- Model used
- Duration per LLM call
- Token usage statistics
- API call results

### Configuration

#### Environment Variables

Required configuration (`.env` file):

```
OPENROUTER_API_KEY=<api-key>    # OpenRouter API access
EC3_API_KEY=<api-key>            # ERC3 platform access
DEBUG=<true|false>               # Enable debug output (optional)
```

#### Dependencies

**Core Libraries:**
- `erc3>=1.1.4` - ERC3 platform SDK
- `openai>=2.9.0` - OpenAI SDK (via OpenRouter)
- `mlflow>=3.7.0` - Experiment tracking
- `python-dotenv>=1.2.1` - Environment variable loading

**Additional:**
- `pydantic` - Data validation and structured schemas
- `annotated-types` - Type annotations for constraints

### Limitations & Design Decisions

#### Current Limitations

1. **Fixed Step Limit:** Maximum 20 reasoning steps per task (safety measure)
2. **Single-Step Planning:** Only executes first planned step, discards rest
3. **No Parallel Execution:** Steps execute sequentially
4. **Limited Error Recovery:** Single retry mechanism, no advanced error handling
5. **Hardcoded Task Filtering:** `failed_tasks` list in main.py controls which tasks run

#### Design Rationale

**Why SGR (Schema-Guided Reasoning)?**
- Ensures type-safe API calls (no hallucinated parameters)
- Provides interpretable reasoning chain
- Enables robust testing and validation
- Reduces error rate compared to free-form tool calling

**Why NextStep Pattern?**
- Forces explicit planning before action
- Enables easy logging and debugging
- Provides checkpoints for human oversight
- Allows task completion detection

**Why Sub-Agent for Current User?**
- Separates concerns (user context vs task execution)
- Enables lazy loading of user data
- Provides dedicated LLM context for user questions
- Reduces main conversation token usage

### Testing Strategy

The agent is designed for the ERC3 benchmark platform which provides:

1. **Automated Evaluation:** Each task has expected outcomes
2. **Score Calculation:** Based on correct API calls and responses
3. **Multiple Benchmarks:**
   - `erc3-dev` - Development/training set
   - `erc3-test` - More complex scenarios with subtle variations
   - `erc3-prod` - Production benchmark (coming soon)

**Evaluation Flow:**
```
1. Agent completes task
2. Platform evaluates response
3. Score + logs returned
4. Results tracked in session
```

### Extension Points

To extend the agent:

1. **Add New API Operations:**
   - Add to `NextStep.function` Union type
   - ERC3 SDK handles dispatch automatically

2. **Add New Sub-Agents:**
   - Create agent class similar to `CurrentUserAgent`
   - Add request model to `NextStep.function`
   - Handle in agent loop

3. **Improve Planning:**
   - Modify `NextStep` schema to include more context
   - Adjust system prompts in `agent.py`

4. **Add Memory/State:**
   - Implement persistent state between tasks
   - Use MLflow for cross-task learning

### File Structure

```
martin-sgr-agent-erc3/
├── main.py                 # Entry point, session management
├── agent.py                # Core SGR reasoning loop
├── current_user_agent.py   # Sub-agent for user context
├── dump_wiki.py            # Wiki download utility
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata
├── .env                    # Environment variables (not in git)
├── wikis/                  # Downloaded wiki content (by task)
│   └── tsk-{id}/
│       ├── rulebook.md
│       ├── people/
│       ├── offices/
│       └── ...
└── mlflow.db              # Local MLflow tracking database
```

## References

- **ERC3 Platform:** https://erc.timetoact-group.at/
- **Schema-Guided Reasoning:** https://abdullin.com/schema-guided-reasoning/
- **SGR NextStep Architecture:** https://abdullin.com/schema-guided-reasoning/demo
- **OpenRouter:** https://openrouter.ai/
- **MLflow:** https://mlflow.org/
