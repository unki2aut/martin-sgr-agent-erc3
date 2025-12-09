import json
import os
from typing import Literal

from instructor import Instructor
from pydantic import BaseModel, Field
from erc3 import Erc3Client
from dotenv import load_dotenv

load_dotenv()

DEBUG = bool(os.getenv("DEBUG", False))

# class Req_ProvideAgentResponse(BaseModel):
#     tool: Literal["/respond"] = "/respond"
#     message: str
#     outcome: Outcome
#     links: List[AgentLink] = Field(default_factory=list)

class CurrentUserQuestion(BaseModel):
    tool: Literal["question_about_current_user"] = "question_about_current_user"
    question: str = Field(..., description="any question about current user")

class CurrentUserAgent:
    _data = list()

    def __init__(self, client: Instructor, model: str, store_api: Erc3Client):
        self.client = client
        self.model = model
        self.store_api = store_api

    def gather_init_data(self):
        if self._data:
            return  # already gathered

        about = self.store_api.who_am_i()

        if not about.current_user:
            self._data.append("No current user found.")
            return

        resp = self.store_api.get_employee(about.current_user)
        employee = None
        if resp.employee:
            employee = resp.employee
            self._data.append(resp.employee.model_dump_json())
        else:
            self._data.append("No employee data found.")

        if employee:
            resp = self.store_api.search_wiki(employee.name)
            if resp.results:
                for item in resp.results:
                    wiki = self.store_api.load_wiki(item.path)
                    extracted_user_info = self._extract_user_info(employee.name, wiki.content)
                    self._data.append(extracted_user_info)
            else:
                self._data.append("No wiki data about the user found.")

    def _extract_user_info(self, name: str, wiki_content: str) -> dict:
        log = [
            {"role": "system", "content": f"Extract information about the person \"{name}\""},
            {"role": "user", "content": wiki_content},
        ]

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=log,
            max_completion_tokens=16384,
        )
        return completion.choices[0].message.content.strip()

    def ask_question(self, question: str) -> str:
        system_prompt = f"""
You are a assistant providing information about the current user in Aetherion system.

# Current user info:
{json.dumps(self._data, indent=2)}
"""
        log = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=log,
            max_completion_tokens=16384,
        )
        answer = completion.choices[0].message.content.strip()

        if DEBUG:
            print(f"\nmodel completion:\n"
                  f"User Info:\n{json.dumps(self._data, indent=2)}\n"
                  f"Question:{question}\nResponse:\n{answer}\n\n")

        return answer
