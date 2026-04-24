```python
"""
ElevenLabs API integration for text-to-speech voiceover generation.

This module handles text-to-speech conversion using the ElevenLabs API,
providing voiceover generation for video content with various voice options
and quality settings.
"""

import os
import json
import logging
import tempfile
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
DEFAULT_MODEL_ID = "eleven_monolingual_v1"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
MAX_TEXT_LENGTH = 5000  # ElevenLabs character limit per request
SUPPORTED_OUTPUT_FORMATS = ["mp3_44100_128", "mp3_44100_64", "mp3_22050_128", "pcm_16000", "pcm_22050", "pcm_24000", "ulaw_8000"]


class ElevenLabsError(Exception):
    """Custom exception for ElevenLabs API errors."""
    pass


class VoiceGenerator:
    """
    Handles text-to-speech conversion using ElevenLabs API.
    
    Provides methods for generating voiceovers with customizable voices,
    models, and output formats. Supports chunking long texts and
    managing API rate limits.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the VoiceGenerator with API credentials.
        
        Args:
            api_key: ElevenLabs API key. If None, reads from ELEVENLABS_API_KEY env variable.
        
        Raises:
            ElevenLabsError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ElevenLabsError(
                "ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.session = requests.Session()
        self.session.headers.update({
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        })
        
        # Cache for voice list
        self._voices_cache: Optional[List[Dict[str, Any]]] = None
        
        logger.info("VoiceGenerator initialized successfully")
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an API request to ElevenLabs with error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests.request()
        
        Returns:
            API response as dictionary
        
        Raises:
            ElevenLabsError: On API errors or network issues
        """
        url = f"{ELEVENLABS_API_BASE_URL}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            # Handle empty responses (e.g., for audio binary data)
            if not response.content:
                return {}
            
            # Try to parse as JSON, return raw content otherwise
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"content": response.content}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"ElevenLabs API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail.get('detail', error_detail)}"
                except (json.JSONDecodeError, AttributeError):
                    error_msg += f" - Status: {e.response.status_code}"
            
            logger.error(error_msg)
            raise ElevenLabsError(error_msg)
    
    def get_voices(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve available voices from ElevenLabs.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh data
        
        Returns:
            List of voice dictionaries with id, name, and other metadata
        
        Raises:
            ElevenLabsError: On API errors
        """
        if self._voices_cache and not force_refresh:
            return self._voices_cache
        
        try:
            response = self._make_request("GET", "voices")
            voices = response.get("voices", [])
            self._voices_cache = voices
            logger.info(f"Retrieved {len(voices)} voices")
            return voices
        except ElevenLabsError as e:
            logger.error(f"Failed to retrieve voices: {e}")
            raise
    
    def get_voice_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find a voice by its name.
        
        Args:
            name: Voice name to search for (case-insensitive)
        
        Returns:
            Voice dictionary if found, None otherwise
        """
        voices = self.get_voices()
        for voice in voices:
            if voice.get("name", "").lower() == name.lower():
                return voice
        return None
    
    def get_voice_settings(self, voice_id: str) -> Dict[str, Any]:
        """
        Get settings for a specific voice.
        
        Args:
            voice_id: ElevenLabs voice ID
        
        Returns:
            Voice settings dictionary
        
        Raises:
            ElevenLabsError: On API errors
        """
        try:
            return self._make_request("GET", f"voices/{voice_id}/settings")
        except ElevenLabsError as e:
            logger.error(f"Failed to get voice settings for {voice_id}: {e}")
            raise
    
    def update_voice_settings(
        self,
        voice_id: str,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True
    ) -> Dict[str, Any]:
        """
        Update settings for a specific voice.
        
        Args:
            voice_id: ElevenLabs voice ID
            stability: Voice stability (0.0 to 1.0)
            similarity_boost: Voice similarity boost (0.0 to 1.0)
            style: Style exaggeration (0.0 to 1.0)
            use_speaker_boost: Enable speaker boost
        
        Returns:
            Updated voice settings
        
        Raises:
            ElevenLabsError: On API errors or invalid parameters
        """
        # Validate parameters
        for param_name, param_value, min_val, max_val in [
            ("stability", stability, 0.0, 1.0),
            ("similarity_boost", similarity_boost, 0.0, 1.0),
            ("style", style, 0.0, 1.0)
        ]:
            if not min_val <= param_value <= max_val:
                raise ElevenLabsError(
                    f"{param_name} must be between {min_val} and {max_val}"
                )
        
        settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost
        }
        
        try:
            return self._make_request(
                "POST",
                f"voices/{voice_id}/settings/edit",
                json=settings
            )
        except ElevenLabsError as e:
            logger.error(f"Failed to update voice settings for {voice_id}: {e}")
            raise
    
    def generate_speech(
        self,
        text: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        voice_settings: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None
    ) -> Tuple[bytes, Optional[str]]:
        """
        Generate speech audio from text.
        
        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID
            model_id: Model ID for speech generation
            output_format: Audio output format
            voice_settings: Optional voice settings override
            output_path: Optional file path to save audio
        
        Returns:
            Tuple of (audio_bytes, output_path or None)
        
        Raises:
            ElevenLabsError: On API errors or invalid parameters
        """
        if not text or not text.strip():
            raise ElevenLabsError("Text cannot be empty")
        
        if len(text) > MAX_TEXT_LENGTH:
            logger.warning(
                f"Text length ({len(text)}) exceeds maximum ({MAX_TEXT_LENGTH}). "
                "Consider using generate_long_speech() for chunking."
            )
        
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ElevenLabsError(
                f"Unsupported output format: {output_format}. "
                f"Supported formats: {SUPPORTED_OUTPUT_FORMATS}"
            )
        
        # Prepare request payload
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings or {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        params = {
            "output_format": output_format
        }
        
        try:
            response = self.session.post(
                f"{ELEVENLABS_API_BASE_URL}/text-to-speech/{voice_id}",
                json=payload,
                params=params,
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            
            audio_bytes = response.content
            
            # Save to file if output path provided
            saved_path = None
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(audio_bytes)
                saved_path = str(output_path)
                logger.info(f"Speech saved to {saved_path}")
            
            logger.info(f"Generated speech: {len(audio_bytes)} bytes")
            return audio_bytes, saved_path
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Speech generation failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail.get('detail', error_detail)}"
                except (json.JSONDecodeError, AttributeError):
                    error_msg += f" - Status: {e.response.status_code}"
            
            logger.error(error_msg)
            raise ElevenLabsError(error_msg)
    
    def generate_long_speech(
        self,
        text: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        voice_settings: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None,
        chunk_size: int = MAX_TEXT_LENGTH
    ) -> Tuple[bytes, Optional[str]]:
        """
        Generate speech for long texts by chunking.
        
        Splits long text into manageable chunks and concatenates the audio.
        
        Args:
            text: Long text to convert to speech
            voice_id: ElevenLabs voice ID
            model_id: Model ID for speech generation
            output_format: Audio output format
            voice_settings: Optional voice settings override
            output_path: Optional file path to save audio
            chunk_size: Maximum characters per chunk
        
        Returns:
            Tuple of (combined_audio_bytes, output_path or None)
        
        Raises:
            ElevenLabsError: On API errors
        """
        if not text or not text.strip():
            raise ElevenLabsError("Text cannot be empty")
        
        if len(text) <= chunk_size:
            return self.generate_speech(
                text, voice_id, model_id, output_format,
                voice_settings, output_path
            )
        
        # Split text into sentences for natural chunking
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                current_chunk += (" " + sentence) if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"Split long text into {len(chunks)} chunks")
        
        # Generate speech for each chunk
        audio_segments = []
        temp_files = []
        
        try:
            for i, chunk in enumerate(chunks):
                logger.info(f"Generating speech for chunk {i + 1}/{len(chunks)}")
                
                # Create temporary file for each chunk
                with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False
                ) as temp_file:
                    temp_path = temp_file.name
                    temp_files.append(temp_path)
                
                audio_bytes, _ = self.generate_speech(
                    chunk, voice_id, model_id, output_format,
                    voice_settings, temp_path
                )
                audio_segments.append(audio_bytes)
            
            # Combine audio segments
            combined_audio = self._combine_audio(audio_segments)
            
            # Save combined audio if output path provided
            saved_path = None
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(combined_audio)
                saved_path = str(output_path)
                logger.info(f"Combined speech saved to {saved_path}")
            
            return combined_audio, saved_path
            
        finally:
            # Clean up temporary files
            for temp_path in temp_files:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_path}: {e}")
    
    def _combine_audio(self, audio_segments: List[bytes]) -> bytes:
        """
        Combine multiple audio segments into one.
        
        For MP3 files, this concatenates the raw bytes.
        For more sophisticated combining, consider using pydub or ffmpeg.
        
        Args:
            audio_segments: List of audio byte strings
        
        Returns:
            Combined audio bytes
        """
        if not audio_segments:
            return b""
        
        if len(audio_segments) == 1:
            return audio_segments[0]
        
        # Simple concatenation for MP3 files
        # Note: For production, consider using pydub or ffmpeg for proper concatenation
        combined = bytearray()
        for segment in audio_segments:
            combined.extend(segment)
        
        return bytes(combined)
    
    def get_models(self) -> List[Dict[str, Any]]:
        """
        Retrieve available models from ElevenLabs.
        
        Returns:
            List of model dictionaries
        
        Raises:
            ElevenLabsError: On API errors
        """
        try:
            response = self._make_request("GET", "models")
            return response.get("models", [])
        except ElevenLabsError as e:
            logger.error(f"Failed to retrieve models: {e}")
            raise
    
    def get_remaining_characters(self) -> int:
        """
        Get remaining character quota for the API key.
        
        Returns:
            Number of remaining characters
        
        Raises:
            ElevenLabsError: On API errors
        """
        try:
            response = self._make_request("GET", "user/subscription")
            return response.get("character_count", 0)
        except ElevenLabsError as e:
            logger.error(f"Failed to get remaining characters: {e}")
            raise
    
    def get_subscription_info(self) -> Dict[str, Any]:
        """
        Get subscription information for the API key.
        
        Returns:
            Subscription info dictionary
        
        Raises:
            ElevenLabsError: On API errors
        """
        try:
            return self._make_request("GET", "user/subscription")
        except ElevenLabsError as e:
            logger.error(f"Failed to get subscription info: {e}")
            raise


# Convenience function for quick speech generation
def generate_voiceover(
    text: str,
    voice_name: str = "Rachel",
    output_path: Optional[str] = None,
    **kwargs
) -> Tuple[bytes, Optional[str]]:
    """
    Quick voiceover generation with default settings.
    
    Args:
        text: Text to convert to speech
        voice_name: Name of the voice to use (default: Rachel)
        output_path: Optional file path to save audio
        **kwargs: Additional arguments for VoiceGenerator.generate_speech()
    
    Returns:
        Tuple of (audio_bytes, output_path or None)
    
    Raises:
        ElevenLabsError: On API errors
    """
    generator = VoiceGenerator()
    
    # Find voice by name
    voice = generator.get_voice_by_name(voice_name)
    if not voice:
        logger.warning(f"Voice '{voice_name}' not found. Using default voice.")
        voice_id = DEFAULT_VOICE_ID
    else:
        voice_id = voice["voice_id"]
    
    return generator.generate_speech(
        text=text,
        voice_id=voice_id,
        output_path=output_path,
        **kwargs
    )


# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    try:
        # Initialize voice generator
        generator = VoiceGenerator()
        
        # Get available voices
        voices = generator.get_voices()
        print