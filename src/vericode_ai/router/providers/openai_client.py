import os
from openai import OpenAI
from vericode_ai.router.llm_router import BaseLLM

class OpenAIProvider(BaseLLM):
    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.client:
            raise ValueError("OpenAI API key not configured")
            
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.0)
        )
        return response.choices[0].message.content
