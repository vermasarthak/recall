"""
Recall Showcase: The AI Chat Companion

This example demonstrates how to integrate the Recall engine into an AI agent's loop.
It uses the local, embedded Recall engine to extract facts from the user's input,
semantically search the memory graph, and construct an XML prompt context.

To run with a real LLM, export your OPENAI_API_KEY. Otherwise, it runs in simulation mode.
"""

import os
import sys
from uuid import uuid4

# Add the parent directory to the path so we can import recall
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recall.client import Recall

def get_llm_response(user_input: str, memory_xml: str) -> str:
    """Simulates an LLM call. If OPENAI_API_KEY is present, it uses the real OpenAI API."""
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.OpenAI()
            prompt = f"You are a helpful companion. You have access to the following memory context about the user:\n{memory_xml}\n\nUser says: {user_input}\nRespond naturally."
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150
            )
            return response.choices[0].message.content
        except ImportError:
            pass
            
    # Simulation Fallback
    if "<memory" in memory_xml and "</memory>" in memory_xml and len(memory_xml) > 50:
        return f"[Simulated LLM] I see in my memory that you mentioned something related! Context provided:\n{memory_xml}\n\nHow can I help you with that today?"
    return "[Simulated LLM] I am listening! Tell me about yourself."

def main():
    print("==========================================================")
    print("🧠 Recall Example: Terminal AI Companion")
    print("==========================================================\n")
    
    # Initialize the local Recall engine
    db_path = "companion_memory.db"
    
    # We use a static tenant/user for this example
    USER_NAME = "User"
    CONVERSATION_ID = f"conv_{uuid4().hex[:8]}"
    
    print(f"Initializing Recall engine at '{db_path}'...")
    
    with Recall(db_path=db_path) as memory_engine:
        print("Ready! Type 'quit' or 'exit' to stop.\n")
        
        while True:
            try:
                user_input = input(f"{USER_NAME}: ")
                if user_input.lower() in ['quit', 'exit']:
                    break
                if not user_input.strip():
                    continue
                
                # 1. RETRIEVE: Semantic Search the memory graph using the user's input
                # We use a low min_score to demonstrate partial matches in the simulation.
                search_results = memory_engine.search(query=user_input, limit=3, min_score=0.1)
                
                # 2. CONSTRUCT: Format the retrieved results into an LLM-friendly XML block
                memory_xml = "<memory></memory>"
                if search_results:
                    # In a real app, you'd use format_for_prompt on the specific entity. 
                    # Here we manually construct it from the global search results.
                    xml_parts = [f"<memory entity='{USER_NAME}'>"]
                    for r in search_results:
                        xml_parts.append(f"  <fact confidence='{r.fact.confidence}'>{r.fact.predicate} {r.fact.object_value}</fact>")
                    xml_parts.append("</memory>")
                    memory_xml = "\n".join(xml_parts)
                
                # 3. RESPOND: Pass the user input and the memory XML to the LLM
                reply = get_llm_response(user_input, memory_xml)
                print(f"\nCompanion: {reply}\n")
                
                # 4. INGEST: Extract facts from the user's input asynchronously 
                # (In this sync example, we just call it directly)
                memory_engine.ingest_turn(
                    speaker=USER_NAME,
                    text=user_input,
                    conversation_id=CONVERSATION_ID
                )
                
            except KeyboardInterrupt:
                break
                
    print("\nGoodbye! Memory saved to companion_memory.db")

if __name__ == "__main__":
    main()
