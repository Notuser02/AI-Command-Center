import os
from dotenv import load_dotenv


load_dotenv()


class NebiusProvider:

    def __init__(self):
        self.api_key = os.getenv("NEBIUS_API_KEY")

    def generate(self, prompt):
        if not self.api_key:
            return "Nebius API key is not configured."

        return "Nebius provider is ready."