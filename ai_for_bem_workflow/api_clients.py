import anthropic
from openai import OpenAI
from google import genai
from api_keys import *
import requests
import json

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

class OpenRouterAPIClient:
    def __init__(self, model_name, max_messages=2):
        self.api_key = openrouter_api_key
        self.model = model_name
        self.messages = []
        self.max_messages = max_messages
        self.history = []

    def call_client(self, prompt):
        self.append_messages({"role": "user", "content": prompt})
        response = self.call_api()
        message = response.json()["choices"][0]["message"]["content"]
        self.append_messages({"role": "assistant", "content": message})
        self.trim_messages()
        return message

    def trim_messages(self):
        trim_len = len(self.messages)-self.max_messages
        self.messages = self.messages[trim_len:]

    def call_api(self):
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data=json.dumps({
                "model": self.model,
                "messages": self.messages
            })
        )
        return response

    def append_messages(self, entry):
        self.messages.append(entry)
        self.history.append(entry)

    def save_history(self, file_path):
        with open(file_path, 'w') as f:
            json.dump(self.history, f, indent=4)

    def get_all_models(self, provider = ""):
        # google, qwen, openai, anthropic, deepseek, openrouter/free
        url = "https://openrouter.ai/api/v1/models/user"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = requests.get(url, headers=headers)
        models = response.json()["data"]
        fltr = [models[x]["id"] for x in range(len(models)) if provider in models[x]["id"]]
        print("\n".join(fltr))

    def get_model_details(self, model_id):
        url = "https://openrouter.ai/api/v1/models/user"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = requests.get(url, headers=headers)
        models = response.json()["data"]
        fltr = [models[x] for x in range(len(models)) if model_id in models[x]["id"]]
        for key, value in fltr[0].items():
            print(f"{key}: {value}")

    def get_credit(self):
        url = "https://openrouter.ai/api/v1/credits"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = requests.get(url, headers=headers)
        print(response.json())


def main():
    my_client = OpenRouterAPIClient("openrouter/free")
    response = my_client.call_client("What is 2 plus 3")
    print(my_client.messages[-1]['content'])
    response = my_client.call_client("add 4 to your previous answer")
    print(my_client.messages[-1]['content'])
    response = my_client.call_client("add 3 to your previous answer")
    print(my_client.messages[-1]['content'])
    print(my_client.history)
    # my_client.get_all_models("openai")
    # my_client.get_model_details("openai/gpt-5.2-pro")
    # my_client.get_credit()


if __name__ == "__main__":
    main()



