from typing import Optional
from app.providers.llm.base import BaseLLMProvider
from app.core.config import settings
from app.core.exceptions import ProviderError

class GeminiLLMProvider(BaseLLMProvider):
    name: str = "gemini"

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self._client = None

    def _get_client(self):
        if not self._client:
            if not self.api_key:
                raise ProviderError("Gemini API key is not configured in environment.")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        client = self._get_client()
        try:
            # google-genai async support
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"temperature": temperature, "system_instruction": system_instruction}
                if system_instruction else {"temperature": temperature},
            )
            return response.text or ""
        except Exception as e:
            raise ProviderError(f"Gemini API generation error: {str(e)}")
