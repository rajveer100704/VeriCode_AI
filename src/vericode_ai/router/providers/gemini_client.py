import os
import google.generativeai as genai
from vericode_ai.router.llm_router import BaseLLM

class GeminiProvider(BaseLLM):
    def __init__(self, api_key: str = None, model: str = "gemini-1.5-pro-latest"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Use safety settings, etc via raw SDK
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.model:
            raise ValueError("Gemini API key not configured")
            
        temperature = kwargs.get("temperature", 0.0)
        
        # Generation configuration bridging
        config = genai.types.GenerationConfig(temperature=temperature)
        
        response = self.model.generate_content(prompt, generation_config=config)
        return response.text
