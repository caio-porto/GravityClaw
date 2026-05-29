import os
import sys
from src.agent.loop import AgentLoop

def main():
    print("=======================================")
    print(" GravityClaw Interactive CLI Test")
    print("=======================================")
    print("Type 'exit' or 'quit' to stop.")
    
    try:
        agent = AgentLoop()
    except Exception as e:
        print(f"Failed to initialize AgentLoop: {e}")
        sys.exit(1)

    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit']:
                break
                
            print("Agent is thinking...")
            response = agent.process_input(user_input)
            print(f"GravityClaw: {response}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error during processing: {e}")

if __name__ == "__main__":
    main()
