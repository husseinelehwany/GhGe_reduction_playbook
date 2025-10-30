import anthropic
from openai import OpenAI
from google import genai
from api_keys import *

class ClaudeAPIClient:

    def __init__(self, model_name, max_tokens):
        self.api_key = claude_api_key
        self.model = model_name #"claude-sonnet-4-20250514",  # "claude-sonnet-4-20250514",  # or claude-3-opus-20240229
        self.max_tokens = max_tokens # 10000
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def call_client(self, prompt)-> str:
        message = self.client.messages.create(
            model= self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

class DeepseekAPIClient:
    def __init__(self, model_name):
        self.api_key = deepseek_api_key
        self.model = model_name
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")

    def call_client(self, prompt)-> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.7,
            messages=[{"role": "user","content": prompt}
          ]
        )

        return response.choices[0].message.content


class OpenaiAPIClient:
    def __init__(self, model_name):
        self.api_key = openai_api_key
        self.model = model_name
        self.client = OpenAI(api_key=self.api_key, base_url="")

    def call_client(self, prompt)-> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}
                      ]
        )

        return response.choices[0].message.content

class GeminiAPIClient:
    def __init__(self, model_name):
        self.api_key = gemini_api_key
        self.model = model_name
        self.client = genai.Client(api_key=self.api_key)

    def call_client(self, prompt) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text

class GeminiChats:
    def __init__(self, model_name):
        self.api_key = gemini_api_key
        self.model = model_name
        self.client = genai.Client(api_key=self.api_key)
        self.chat = self.client.chats.create(model=self.model)

    def call_client(self, prompt) -> str:
        response = self.chat.send_message(
            message=prompt
        )
        return response.text

    def get_history(self):
        history = []
        for message in self.chat.get_history():
            tmp_dict = {"role": message.role, "message": message.parts[0].text}
            history.append(tmp_dict)
        return history


