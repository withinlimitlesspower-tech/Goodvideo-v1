```python
"""
Handlers for DeepSeek API integration for prompt understanding and script generation.
This module provides functions to interact with the DeepSeek API for understanding
user prompts and generating video scripts with proper structure and formatting.
"""

import os
import json
import logging
from typing import Optional, Dict, List, Any, Union
from datetime import datetime

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEFAULT_MODEL = "deepseek-chat"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60

# System prompts for different contexts
SYSTEM_PROMPTS = {
    "script_generation": """You are an expert video script writer. Generate a complete video script based on the user's prompt.
The script should include:
1. A compelling hook/introduction
2. Main content with clear sections
3. A strong call-to-action conclusion
4. Visual cues and scene descriptions in [brackets]
5. Estimated duration for each section

Format the response as a JSON object with the following structure:
{
    "title": "Video Title",
    "description": "Brief video description",
    "sections": [
        {
            "id": 1,
            "type": "intro|content|conclusion",
            "duration_seconds": 15,
            "text": "Narration text",
            "visual_cue": "Scene description",
            "keywords": ["keyword1", "keyword2"]
        }
    ],
    "total_duration_seconds": 60,
    "tone": "professional|casual|educational|entertaining",
    "target_audience": "Description of target audience"
}""",

    "prompt_understanding": """Analyze the user's video creation request and extract key information.
Return a JSON object with:
{
    "topic": "Main topic of the video",
    "style": "Video style (educational, entertaining, promotional, etc.)",
    "target_audience": "Intended audience",
    "key_points": ["Point 1", "Point 2"],
    "suggested_visuals": ["Visual 1", "Visual 2"],
    "suggested_music_mood": "Music mood/theme",
    "duration_preference": "short|medium|long",
    "additional_requirements": ["Requirement 1"]
}""",

    "script_refinement": """You are an expert video editor. Refine the following video script based on user feedback.
Maintain the original structure but improve the content as requested.
Return the refined script in the same JSON format as the original.""",

    "keyword_extraction": """Extract relevant keywords and search terms from the following video script or topic.
These keywords will be used to search for stock footage and images.
Return a JSON array of objects with:
{
    "keywords": [
        {
            "term": "search term",
            "category": "nature|technology|people|business|abstract",
            "priority": 1
        }
    ]
}"""
}


class DeepSeekClient:
    """
    Client for interacting with the DeepSeek API.
    Handles authentication, request formatting, and response parsing.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the DeepSeek client.

        Args:
            api_key: DeepSeek API key. If None, uses DEEPSEEK_API_KEY env variable.
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError(
                "DeepSeek API key is required. Set DEEPSEEK_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.client = httpx.Client(
            base_url="https://api.deepseek.com",
            headers=self.headers,
            timeout=TIMEOUT_SECONDS
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    async def generate_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a completion using the DeepSeek API.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            model: Model name to use
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response

        Returns:
            API response dictionary

        Raises:
            httpx.HTTPError: If API request fails
            ValueError: If response is invalid
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.post(
                    "/v1/chat/completions",
                    json=payload
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error on attempt {attempt + 1}: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

            except httpx.TimeoutException as e:
                logger.error(f"Timeout on attempt {attempt + 1}: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

        raise RuntimeError("Failed to generate completion after all retries")

    def parse_json_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse JSON content from API response.

        Args:
            response: Raw API response dictionary

        Returns:
            Parsed JSON object or None if parsing fails
        """
        try:
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Try to extract JSON from the response
            # Handle cases where JSON is wrapped in markdown code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            return json.loads(json_str)

        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response content: {content}")
            return None

    def extract_text_content(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Extract plain text content from API response.

        Args:
            response: Raw API response dictionary

        Returns:
            Text content or None if extraction fails
        """
        try:
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except (IndexError, KeyError) as e:
            logger.error(f"Failed to extract text content: {e}")
            return None


class ScriptGenerator:
    """
    Handles script generation and prompt understanding using DeepSeek API.
    """

    def __init__(self, client: Optional[DeepSeekClient] = None):
        """
        Initialize the ScriptGenerator.

        Args:
            client: DeepSeekClient instance. If None, creates a new one.
        """
        self.client = client or DeepSeekClient()

    async def understand_prompt(self, user_prompt: str) -> Dict[str, Any]:
        """
        Analyze and understand the user's video creation prompt.

        Args:
            user_prompt: User's video creation request

        Returns:
            Dictionary with analyzed prompt information

        Raises:
            ValueError: If prompt is empty or invalid
        """
        if not user_prompt or not user_prompt.strip():
            raise ValueError("User prompt cannot be empty")

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPTS["prompt_understanding"]
            },
            {
                "role": "user",
                "content": f"Analyze this video creation request: {user_prompt}"
            }
        ]

        try:
            response = await self.client.generate_completion(
                messages=messages,
                temperature=0.3  # Lower temperature for more consistent analysis
            )

            parsed = self.client.parse_json_response(response)
            if parsed:
                parsed["original_prompt"] = user_prompt
                parsed["timestamp"] = datetime.utcnow().isoformat()
                return parsed

            # Fallback to basic analysis if parsing fails
            return self._fallback_analysis(user_prompt)

        except Exception as e:
            logger.error(f"Failed to understand prompt: {e}")
            return self._fallback_analysis(user_prompt)

    async def generate_script(
        self,
        prompt_analysis: Dict[str, Any],
        additional_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete video script based on prompt analysis.

        Args:
            prompt_analysis: Dictionary from understand_prompt()
            additional_instructions: Optional additional instructions for script generation

        Returns:
            Dictionary with complete video script structure

        Raises:
            ValueError: If prompt_analysis is invalid
        """
        if not prompt_analysis:
            raise ValueError("Prompt analysis cannot be empty")

        topic = prompt_analysis.get("topic", "General Video")
        style = prompt_analysis.get("style", "educational")
        key_points = prompt_analysis.get("key_points", [])
        audience = prompt_analysis.get("target_audience", "general audience")

        user_content = f"""Create a video script about: {topic}
Style: {style}
Target Audience: {audience}
Key Points to Cover: {', '.join(key_points)}"""

        if additional_instructions:
            user_content += f"\nAdditional Instructions: {additional_instructions}"

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPTS["script_generation"]
            },
            {
                "role": "user",
                "content": user_content
            }
        ]

        try:
            response = await self.client.generate_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )

            parsed = self.client.parse_json_response(response)
            if parsed:
                parsed["generated_at"] = datetime.utcnow().isoformat()
                parsed["prompt_analysis"] = prompt_analysis
                return parsed

            # Fallback to simple script structure
            return self._fallback_script(topic, style, key_points)

        except Exception as e:
            logger.error(f"Failed to generate script: {e}")
            return self._fallback_script(topic, style, key_points)

    async def refine_script(
        self,
        original_script: Dict[str, Any],
        user_feedback: str
    ) -> Dict[str, Any]:
        """
        Refine an existing script based on user feedback.

        Args:
            original_script: Original script dictionary
            user_feedback: User's feedback and refinement requests

        Returns:
            Refined script dictionary
        """
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPTS["script_refinement"]
            },
            {
                "role": "user",
                "content": f"""Original Script: {json.dumps(original_script, indent=2)}
User Feedback: {user_feedback}

Please refine the script according to the feedback while maintaining the structure."""
            }
        ]

        try:
            response = await self.client.generate_completion(
                messages=messages,
                temperature=0.5,
                max_tokens=4000
            )

            parsed = self.client.parse_json_response(response)
            if parsed:
                parsed["refined_at"] = datetime.utcnow().isoformat()
                parsed["original_script_id"] = original_script.get("title", "unknown")
                return parsed

            return original_script

        except Exception as e:
            logger.error(f"Failed to refine script: {e}")
            return original_script

    async def extract_keywords(
        self,
        script_or_topic: Union[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract search keywords from a script or topic.

        Args:
            script_or_topic: Script dictionary or topic string

        Returns:
            List of keyword dictionaries with term, category, and priority
        """
        if isinstance(script_or_topic, dict):
            content = json.dumps(script_or_topic, indent=2)
        else:
            content = script_or_topic

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPTS["keyword_extraction"]
            },
            {
                "role": "user",
                "content": f"Extract keywords from: {content}"
            }
        ]

        try:
            response = await self.client.generate_completion(
                messages=messages,
                temperature=0.2,
                max_tokens=2000
            )

            parsed = self.client.parse_json_response(response)
            if parsed and "keywords" in parsed:
                return parsed["keywords"]

            return []

        except Exception as e:
            logger.error(f"Failed to extract keywords: {e}")
            return []

    def _fallback_analysis(self, prompt: str) -> Dict[str, Any]:
        """
        Provide a basic analysis when API call fails.

        Args:
            prompt: Original user prompt

        Returns:
            Basic analysis dictionary
        """
        return {
            "topic": prompt[:100],
            "style": "educational",
            "target_audience": "general",
            "key_points": [prompt],
            "suggested_visuals": ["relevant stock footage"],
            "suggested_music_mood": "neutral",
            "duration_preference": "medium",
            "additional_requirements": [],
            "original_prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(),
            "fallback": True
        }

    def _fallback_script(
        self,
        topic: str,
        style: str,
        key_points: List[str]
    ) -> Dict[str, Any]:
        """
        Generate a simple fallback script structure.

        Args:
            topic: Video topic
            style: Video style
            key_points: List of key points to cover

        Returns:
            Basic script dictionary
        """
        sections = []
        duration = 0

        # Introduction
        sections.append({
            "id": 1,
            "type": "intro",
            "duration_seconds": 15,
            "text": f"Welcome to this {style} video about {topic}.",
            "visual_cue": f"Animated title: {topic}",
            "keywords": [topic]
        })
        duration += 15

        # Content sections
        for i, point in enumerate(key_points, start=2):
            section_duration = 20
            sections.append({
                "id": i,
                "type": "content",
                "duration_seconds": section_duration,
                "text": f"Let's explore {point}.",
                "visual_cue": f"Visual representation of {point}",
                "keywords": [point]
            })
            duration += section_duration

        # Conclusion
        sections.append({
            "id": len(key_points) + 2,
            "type": "conclusion",
            "duration_seconds": 15,
            "text": f"Thanks for watching! Don't forget to like and subscribe for more {style} content.",
            "visual_cue": "Call to action with subscribe button",
            "keywords": ["subscribe", "like", topic]
        })
        duration += 15

        return {
            "title": topic,
            "description": f"A {style} video about {topic}",
            "sections": sections,
            "total_duration_seconds": duration,
            "tone": "educational",
            "target_audience": "general",
            "generated_at": datetime.utcnow().isoformat(),
            "fallback": True
        }


# Convenience functions for common operations

async def analyze_prompt(prompt: str) -> Dict[str, Any]:
    """
    Convenience function to analyze a video creation prompt.

    Args:
        prompt: User's video creation request

    Returns:
        Analyzed prompt information
    """
    async with DeepSeekClient() as client:
        generator = ScriptGenerator(client)
        return await generator.understand_prompt(prompt)


async def create_script(
    prompt_analysis: Dict[str, Any],
    instructions: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to generate a video script.

    Args:
        prompt_analysis: Analyzed prompt from analyze_prompt()
        instructions: Optional additional instructions

    Returns:
        Complete video script
    """
    async with DeepSeekClient() as client:
        generator = ScriptGenerator(client)
        return await generator.generate_script(prompt_analysis, instructions)


async def get_keywords(script_or_topic: Union[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function to extract keywords.

    Args:
        script_or_topic: Script or topic to extract keywords from

    Returns:
        List of keyword dictionaries
    """
    async with DeepSeekClient() as client:
        generator = ScriptGenerator(client)
        return await generator.extract_keywords(script_or_topic)


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        """Example usage of the chat handlers."""
        try:
            # Example 1: Analyze a prompt
            prompt = "Create an educational video about machine learning basics for beginners"
            analysis = await analyze_prompt