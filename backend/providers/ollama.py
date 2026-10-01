import requests


class OllamaProvider:

    def __init__(self, model="qwen3.5:9b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def generate(self, prompt):
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        result = response.json()

        return result["response"]
    
    
if __name__ == "__main__":
    providers = OllamaProvider()

    answer = providers.generate("Explain what an API is in one sentence.")

    print(answer)