class Agent:

    def __init__(self, provider):
        self.provider = provider
        self.status = "idle"
        self.result = None

    def run(self, task):
        self.status = "running"

        self.result = self.provider.generate(task)

        self.status = "completed"

        return self.result