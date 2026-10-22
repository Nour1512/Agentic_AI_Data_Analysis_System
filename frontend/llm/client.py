import os
from groq import Groq

class LLMClient:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = self._get_groq_model()

    def _get_groq_model(self) -> str:
        try:
            models_data = self.client.models.list().data
            available_models = [m.id for m in models_data]
            
            # Using current available open source models on Groq
            preferred_models = [
                      # Strongest free model — best for complex SQL/reasoning
                "openai/gpt-oss-120b",       # Faster, lighter fallback
                "qwen/qwen3.6-27b"
            ]
            
            for model in preferred_models:
                if model in available_models:
                    return model
                    
            if available_models:
                return available_models[0]
                
        except Exception as e:
            print(f"WARNING: Failed to fetch models from Groq API: {e}")
            
        return "llama3-70b-8192"

    def generate(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> str:
        import time
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0
                )
                return response.choices[0].message.content
            except Exception as e:
                last_error = e
                print(f"WARNING: LLM API error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s...
        
        raise Exception(f"Failed to generate after {max_retries} attempts. Last error: {last_error}")
