import asyncio
from gigoptimizer.assistant.assistant import AIAssistant
from gigoptimizer.config import GigOptimizerConfig

async def test_copilot():
    config = GigOptimizerConfig()
    assistant = AIAssistant(
        llm_provider="ollama", 
        llm_model="deepseek-r1:1.5b", 
        use_fallback=True
    )
    
    print("Sending message to Copilot...")
    response = assistant.chat(
        message="What is the best way to optimize my gig?",
        ui_context={},
        gig_id="test_gig",
    )
    
    print("\n--- COPILOT RESPONSE ---")
    print(response.raw_text)
    print("------------------------")

if __name__ == "__main__":
    asyncio.run(test_copilot())
