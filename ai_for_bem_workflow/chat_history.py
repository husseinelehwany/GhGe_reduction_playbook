import json

class ChatHistory:
    def __init__(self, max_messages=10, max_tokens=150000):
        """
        Initialize the chat history manager

        Args:
            max_messages (int): Maximum number of messages to keep
            max_tokens (int): Maximum token limit for context
        """
        self.messages = []
        self.max_messages = max_messages
        self.max_tokens = max_tokens

    def append(self, role, content):
        message = {
            "role": role,
            "content": content
        }
        self.messages.append(message)

    def trim_by_count(self):
        """Remove oldest messages to stay within max_messages limit"""
        if len(self.messages) > self.max_messages:
            excess = len(self.messages) - self.max_messages
            self.messages = self.messages[excess:]
            return excess
        return 0

    def get(self):
        return self.messages

    def save(self, file_path):
        history = self.chat_history.get()
        with open(file_path, 'w') as f:
            json.dump(history, f, indent=4)

