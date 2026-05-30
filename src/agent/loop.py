import os
import re
import yaml
import logging
import requests
import subprocess
from typing import Dict, List

from src.memory.core import CoreMemory
from src.memory.buffer import DailyBuffer

logger = logging.getLogger(__name__)


class ModelManager:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.models = self.config.get("models", {})

    def query(self, messages: List[Dict[str, str]]) -> str:
        """Send a multi-turn conversation to the model.
        
        Args:
            messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        """
        # Try primary model (Antigravity CLI via subprocess)
        try:
            return self._query_antigravity(messages)
        except Exception as e:
            logger.warning(f"Primary model failed: {e}. Falling back...")
            return self._query_fallback(messages)

    def _query_antigravity(self, messages: List[Dict[str, str]]) -> str:
        """Invokes the locally installed Antigravity CLI via subprocess.
        
        The CLI only accepts a single --prompt string, so we flatten the
        messages into a well-structured prompt that preserves conversation flow.
        """
        logger.info("Invoking Antigravity CLI via subprocess...")

        # Flatten messages into a single prompt for the CLI
        prompt = self._flatten_messages_for_cli(messages)
        full_output = self._run_antigravity_cli(prompt)
        return self._clean_antigravity_output(full_output)

    def _run_antigravity_cli(self, prompt: str) -> str:
        """Executes the antigravity CLI and returns raw stdout."""
        cmd = [
            "gemini",
            "--approval-mode", "yolo",
            "--output-format", "text",
            "--allowed-mcp-server-names", "none",
            "--prompt", prompt
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/app", timeout=60)
        
        if result.returncode != 0 and result.returncode != 42:
            raise RuntimeError(f"Antigravity CLI failed with code {result.returncode}: {result.stderr}")
            
        return result.stdout

    def _clean_antigravity_output(self, full_output: str) -> str:
        """Cleans and formats the raw stdout from the antigravity CLI."""
        lines = [
            line for line in full_output.split('\n')
            if line.strip() 
            and 'yolo mode' not in line.lower()
            and 'loaded cached credentials' not in line.lower()
            and 'hook execution' not in line.lower()
            and 'hook(s) failed' not in line.lower()
            and 'color support' not in line.lower()
            and 'ripgrep' not in line.lower()
            and 'pgrep:' not in line.lower()
            and 'greptool' not in line.lower()
            and 'command not found' not in line.lower()
            and 'warning:' not in line.lower()
            and 'falling back to' not in line.lower()
        ]
        
        response = "\n".join(lines).strip()
        marker = "Gemini:"
        if marker in response:
            response = response.split(marker)[-1].strip()
            
        if not response:
            raise RuntimeError("Antigravity CLI returned an empty response.")
            
        return response

    def _flatten_messages_for_cli(self, messages: List[Dict[str, str]]) -> str:
        """Convert a multi-turn messages list into a single CLI prompt string."""
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"[System Instructions]\n{content}")
            elif role == "user":
                parts.append(f"[User]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
        return "\n\n".join(parts)

    def _query_fallback(self, messages: List[Dict[str, str]]) -> str:
        fallbacks = self.models.get("fallback", [])
        for fb in fallbacks:
            if fb.get("provider") == "groq":
                try:
                    return self._query_groq(messages, fb.get("model_name"))
                except Exception as e:
                    logger.warning(f"Groq fallback failed: {e}")
            elif fb.get("provider") == "ollama":
                try:
                    return self._query_ollama(messages, fb.get("model_name"), fb.get("url"))
                except Exception as e:
                    logger.warning(f"Ollama fallback failed: {e}")
        raise RuntimeError("All models failed.")

    def _query_groq(self, messages: List[Dict[str, str]], model_name: str) -> str:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json={
            "model": model_name,
            "messages": messages
        })
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Groq Error Details: {response.text}")
            raise e
        return response.json()["choices"][0]["message"]["content"]

    def _query_ollama(self, messages: List[Dict[str, str]], model_name: str, url: str) -> str:
        # Ollama chat API supports messages format
        response = requests.post(f"{url}/api/chat", json={
            "model": model_name,
            "messages": messages,
            "stream": False
        })
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Ollama Error Details: {response.text}")
            raise e
        return response.json().get("message", {}).get("content", "")


class AgentLoop:
    def __init__(self):
        self.model_manager = ModelManager()
        self.core_memory = CoreMemory()
        self.daily_buffer = DailyBuffer()

    def _parse_history_to_turns(self, raw_history: str) -> List[Dict[str, str]]:
        """Parse the daily buffer markdown into alternating user/assistant message dicts."""
        turns = []
        # Match interaction blocks: ### [timestamp] Interaction with user_id
        blocks = re.split(r'###\s*\[[\d:]+\]\s*Interaction with\s+\S+', raw_history)
        # Also extract the user/assistant pairs from each block
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            user_match = re.search(r'\*\*User\*\*:\s*(.+?)(?=\n\n|\n\*\*GravityClaw\*\*|\Z)', block, re.DOTALL)
            assistant_match = re.search(r'\*\*GravityClaw\*\*:\s*(.+?)(?=\n###|\Z)', block, re.DOTALL)
            
            if user_match:
                user_text = user_match.group(1).strip()
                if user_text and user_text != "Mocked successful response.":
                    # Clean up temporary file references from history
                    user_text = re.sub(r'@temp_(?:photo|voice)_\S+', '[Attached File]', user_text)
                    turns.append({"role": "user", "content": user_text})
            
            if assistant_match:
                assistant_text = assistant_match.group(1).strip()
                if assistant_text and assistant_text != "Mocked successful response.":
                    # Clean up temporary file references from history
                    assistant_text = re.sub(r'@temp_(?:photo|voice)_\S+', '[Attached File]', assistant_text)
                    turns.append({"role": "assistant", "content": assistant_text})
        
        return turns

    def process_input(self, user_input: str, user_id: str = "User", image_path: str = None) -> str:
        # Phase C: Connect - The main agentic loop
        
        # 1. Build system prompt from core memory
        core_context = self.core_memory.get_context()
        system_prompt = (
            f"{core_context}\n\n"
            f"IMPORTANT BEHAVIORAL RULES:\n"
            f"- This is an ongoing conversation. Do NOT greet the user again if you've already been talking.\n"
            f"- Do NOT start every message with 'Hello' or 'Hey'. Just respond naturally.\n"
            f"- Reference previous messages when relevant — you have full conversation history.\n"
            f"- Keep responses concise and conversational.\n"
            f"- Do not proactively state the user's name or ID unless explicitly asked 'What is my name?'. Talk and respond to the user naturally.\n"
            f"- If the user asks for a picture, photo, or image of something, or if you want to visually show them something, you MUST output a special tag in your response: [IMAGE: prompt describing the image in detail]. Example: [IMAGE: a beautiful high-resolution photo of a Rivian R2 electric SUV driving on a highway]. You can generate multiple image tags if requested or appropriate.\n"
            f"- If the user explicitly asks for a picture/image *from the internet* (rather than generating one), you MUST perform a Google search to locate a real, active, direct image URL of that subject, and output a special tag in your response: [IMAGE_URL: https://...]. Do NOT guess, imagine, or hallucinate image URLs (such as guessing upload.wikimedia.org file paths). Every URL inside [IMAGE_URL: ...] MUST be a real, valid direct image link (ending in .jpg, .png, .gif, etc.) retrieved from actual search results. Be smart and relentless in locating direct image assets from your searches.\n"
            f"- The current user's ID is: {user_id}"
        )
        
        # 2. Build conversation history as proper chat turns
        raw_history = self.daily_buffer.get_recent_context(lines=80, max_days=3)
        history_turns = self._parse_history_to_turns(raw_history)
        
        # 3. Construct the messages array
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (limit to last 20 turns to avoid token overflow)
        if history_turns:
            messages.extend(history_turns[-20:])
        
        # Add the current user message
        full_user_input = user_input
        if image_path:
            # Append image path using @ syntax for gemini CLI
            if full_user_input:
                full_user_input += f" @{image_path}"
            else:
                full_user_input = f"@{image_path}"
                
        messages.append({"role": "user", "content": full_user_input})
        
        # 4. Generate response using ModelManager
        response = self.model_manager.query(messages)
        
        # 5. Save interaction to daily buffer
        self.daily_buffer.add_interaction(user_id, full_user_input, response)
        
        return response
