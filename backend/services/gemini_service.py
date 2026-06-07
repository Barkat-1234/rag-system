import os
from google import genai

# Get API key from environment variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# For development - you can also set it directly temporarily
if not GEMINI_API_KEY:
    # Remove this after setting environment variable
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # 👈 Replace with your actual key for now
    print("⚠️ Using hardcoded API key - please set GEMINI_API_KEY environment variable")

# Initialize the new Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

class GeminiService:
    def __init__(self):
        self.model_name = 'gemini-2.0-flash-exp'  # Latest model
    
    def generate_answer(self, query: str, context: str) -> str:
        """Generate answer using Gemini based on retrieved context"""
        prompt = f"""You are a helpful assistant. Answer the question based ONLY on the provided context.

Context: {context}

Question: {query}

Answer (be concise and accurate):"""
        
        try:
            # Using the new SDK syntax
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"Gemini generation error: {e}")
            return f"Error generating response: {e}"

# Create global instance
gemini_service = GeminiService()
print("✅ Gemini Service initialized successfully with new SDK!")