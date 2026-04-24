```python
"""
Configuration file for AI Video Generator application.

This module handles loading and validation of all configuration settings,
including API keys for DeepSeek, Pixabay, and ElevenLabs services,
as well as application-level settings.

Environment variables are loaded from a .env file if present.
"""

import os
import sys
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class Config:
    """
    Application configuration manager.
    
    Loads and validates configuration from environment variables,
    with sensible defaults for development and production use.
    
    Attributes:
        DEEPSEEK_API_KEY: API key for DeepSeek AI service
        PIXABAY_API_KEY: API key for Pixabay media service
        ELEVENLABS_API_KEY: API key for ElevenLabs voice synthesis
        ELEVENLABS_VOICE_ID: Default voice ID for ElevenLabs
        DATABASE_PATH: Path to SQLite database file
        LOG_LEVEL: Logging level for the application
        MAX_VIDEO_DURATION: Maximum video duration in seconds
        MAX_VIDEO_SIZE_MB: Maximum video file size in MB
        OUTPUT_DIR: Directory for generated videos
        TEMP_DIR: Directory for temporary files
        ALLOWED_EXTENSIONS: Allowed file extensions
    """
    
    # API Keys
    DEEPSEEK_API_KEY: Optional[str] = None
    PIXABAY_API_KEY: Optional[str] = None
    ELEVENLABS_API_KEY: Optional[str] = None
    
    # ElevenLabs Settings
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
    ELEVENLABS_MODEL: str = "eleven_monolingual_v1"
    ELEVENLABS_STABILITY: float = 0.5
    ELEVENLABS_SIMILARITY_BOOST: float = 0.75
    
    # Application Settings
    DATABASE_PATH: str = "data/video_generator.db"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    
    # Video Settings
    MAX_VIDEO_DURATION: int = 120  # seconds
    MAX_VIDEO_SIZE_MB: int = 100
    DEFAULT_VIDEO_WIDTH: int = 1920
    DEFAULT_VIDEO_HEIGHT: int = 1080
    DEFAULT_FPS: int = 30
    
    # Output Settings
    OUTPUT_DIR: str = "output"
    TEMP_DIR: str = "temp"
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS: set = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    
    # Pixabay Settings
    PIXABAY_SAFE_SEARCH: bool = True
    PIXABAY_VIDEO_QUALITY: str = "high"  # high, medium, low
    PIXABAY_MAX_RESULTS: int = 50
    
    # DeepSeek Settings
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TEMPERATURE: float = 0.7
    DEEPSEEK_MAX_TOKENS: int = 2000
    
    # Chat Settings
    MAX_CHAT_HISTORY: int = 100
    CHAT_HISTORY_EXPIRY_DAYS: int = 30
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW: int = 60  # seconds
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            env_file: Path to .env file (optional)
            
        Raises:
            ConfigurationError: If required configuration is missing
        """
        self._load_env_file(env_file)
        self._load_from_environment()
        self._validate_configuration()
        self._create_directories()
    
    def _load_env_file(self, env_file: Optional[str] = None) -> None:
        """
        Load environment variables from .env file.
        
        Args:
            env_file: Path to .env file. If None, searches in current directory
                     and parent directories.
        """
        if load_dotenv is None:
            print("Warning: python-dotenv not installed. Using system environment variables.")
            return
        
        if env_file:
            env_path = Path(env_file)
            if not env_path.exists():
                raise ConfigurationError(f"Environment file not found: {env_file}")
            load_dotenv(env_path)
        else:
            # Search for .env in current and parent directories
            current_dir = Path.cwd()
            for parent in [current_dir] + list(current_dir.parents):
                env_path = parent / '.env'
                if env_path.exists():
                    load_dotenv(env_path)
                    print(f"Loaded environment from: {env_path}")
                    break
    
    def _load_from_environment(self) -> None:
        """Load configuration values from environment variables."""
        # API Keys
        self.DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
        self.PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')
        self.ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
        
        # ElevenLabs Settings
        self.ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', self.ELEVENLABS_VOICE_ID)
        self.ELEVENLABS_MODEL = os.getenv('ELEVENLABS_MODEL', self.ELEVENLABS_MODEL)
        
        try:
            self.ELEVENLABS_STABILITY = float(
                os.getenv('ELEVENLABS_STABILITY', str(self.ELEVENLABS_STABILITY))
            )
            self.ELEVENLABS_SIMILARITY_BOOST = float(
                os.getenv('ELEVENLABS_SIMILARITY_BOOST', str(self.ELEVENLABS_SIMILARITY_BOOST))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid ElevenLabs numeric setting: {e}")
        
        # Application Settings
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', self.DATABASE_PATH)
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', self.LOG_LEVEL).upper()
        self.SECRET_KEY = os.getenv('SECRET_KEY', self.SECRET_KEY)
        
        # Video Settings
        try:
            self.MAX_VIDEO_DURATION = int(
                os.getenv('MAX_VIDEO_DURATION', str(self.MAX_VIDEO_DURATION))
            )
            self.MAX_VIDEO_SIZE_MB = int(
                os.getenv('MAX_VIDEO_SIZE_MB', str(self.MAX_VIDEO_SIZE_MB))
            )
            self.DEFAULT_VIDEO_WIDTH = int(
                os.getenv('DEFAULT_VIDEO_WIDTH', str(self.DEFAULT_VIDEO_WIDTH))
            )
            self.DEFAULT_VIDEO_HEIGHT = int(
                os.getenv('DEFAULT_VIDEO_HEIGHT', str(self.DEFAULT_VIDEO_HEIGHT))
            )
            self.DEFAULT_FPS = int(
                os.getenv('DEFAULT_FPS', str(self.DEFAULT_FPS))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid video numeric setting: {e}")
        
        # Output Settings
        self.OUTPUT_DIR = os.getenv('OUTPUT_DIR', self.OUTPUT_DIR)
        self.TEMP_DIR = os.getenv('TEMP_DIR', self.TEMP_DIR)
        
        # Pixabay Settings
        self.PIXABAY_SAFE_SEARCH = os.getenv('PIXABAY_SAFE_SEARCH', str(self.PIXABAY_SAFE_SEARCH)).lower() == 'true'
        self.PIXABAY_VIDEO_QUALITY = os.getenv('PIXABAY_VIDEO_QUALITY', self.PIXABAY_VIDEO_QUALITY)
        
        try:
            self.PIXABAY_MAX_RESULTS = int(
                os.getenv('PIXABAY_MAX_RESULTS', str(self.PIXABAY_MAX_RESULTS))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid Pixabay numeric setting: {e}")
        
        # DeepSeek Settings
        self.DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', self.DEEPSEEK_MODEL)
        
        try:
            self.DEEPSEEK_TEMPERATURE = float(
                os.getenv('DEEPSEEK_TEMPERATURE', str(self.DEEPSEEK_TEMPERATURE))
            )
            self.DEEPSEEK_MAX_TOKENS = int(
                os.getenv('DEEPSEEK_MAX_TOKENS', str(self.DEEPSEEK_MAX_TOKENS))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid DeepSeek numeric setting: {e}")
        
        # Chat Settings
        try:
            self.MAX_CHAT_HISTORY = int(
                os.getenv('MAX_CHAT_HISTORY', str(self.MAX_CHAT_HISTORY))
            )
            self.CHAT_HISTORY_EXPIRY_DAYS = int(
                os.getenv('CHAT_HISTORY_EXPIRY_DAYS', str(self.CHAT_HISTORY_EXPIRY_DAYS))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid chat numeric setting: {e}")
        
        # Rate Limiting
        try:
            self.RATE_LIMIT_REQUESTS = int(
                os.getenv('RATE_LIMIT_REQUESTS', str(self.RATE_LIMIT_REQUESTS))
            )
            self.RATE_LIMIT_WINDOW = int(
                os.getenv('RATE_LIMIT_WINDOW', str(self.RATE_LIMIT_WINDOW))
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid rate limit numeric setting: {e}")
    
    def _validate_configuration(self) -> None:
        """
        Validate that all required configuration values are present and valid.
        
        Raises:
            ConfigurationError: If validation fails
        """
        missing_keys = []
        
        # Check required API keys
        if not self.DEEPSEEK_API_KEY:
            missing_keys.append('DEEPSEEK_API_KEY')
        if not self.PIXABAY_API_KEY:
            missing_keys.append('PIXABAY_API_KEY')
        if not self.ELEVENLABS_API_KEY:
            missing_keys.append('ELEVENLABS_API_KEY')
        
        if missing_keys:
            raise ConfigurationError(
                f"Missing required API keys: {', '.join(missing_keys)}. "
                "Please set them in your .env file or environment variables."
            )
        
        # Validate log level
        valid_log_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self.LOG_LEVEL not in valid_log_levels:
            raise ConfigurationError(
                f"Invalid LOG_LEVEL: {self.LOG_LEVEL}. "
                f"Must be one of: {', '.join(valid_log_levels)}"
            )
        
        # Validate numeric ranges
        if not 0 < self.MAX_VIDEO_DURATION <= 600:
            raise ConfigurationError("MAX_VIDEO_DURATION must be between 1 and 600 seconds")
        
        if not 0 < self.MAX_VIDEO_SIZE_MB <= 500:
            raise ConfigurationError("MAX_VIDEO_SIZE_MB must be between 1 and 500 MB")
        
        if not 0 < self.DEFAULT_FPS <= 60:
            raise ConfigurationError("DEFAULT_FPS must be between 1 and 60")
        
        if not 0 <= self.ELEVENLABS_STABILITY <= 1:
            raise ConfigurationError("ELEVENLABS_STABILITY must be between 0 and 1")
        
        if not 0 <= self.ELEVENLABS_SIMILARITY_BOOST <= 1:
            raise ConfigurationError("ELEVENLABS_SIMILARITY_BOOST must be between 0 and 1")
        
        if not 0 < self.DEEPSEEK_TEMPERATURE <= 2:
            raise ConfigurationError("DEEPSEEK_TEMPERATURE must be between 0 and 2")
        
        if not 0 < self.DEEPSEEK_MAX_TOKENS <= 8192:
            raise ConfigurationError("DEEPSEEK_MAX_TOKENS must be between 1 and 8192")
        
        if not 0 < self.PIXABAY_MAX_RESULTS <= 200:
            raise ConfigurationError("PIXABAY_MAX_RESULTS must be between 1 and 200")
        
        if self.PIXABAY_VIDEO_QUALITY not in {'high', 'medium', 'low'}:
            raise ConfigurationError(
                f"Invalid PIXABAY_VIDEO_QUALITY: {self.PIXABAY_VIDEO_QUALITY}. "
                "Must be 'high', 'medium', or 'low'"
            )
        
        if not 0 < self.RATE_LIMIT_REQUESTS <= 1000:
            raise ConfigurationError("RATE_LIMIT_REQUESTS must be between 1 and 1000")
        
        if not 0 < self.RATE_LIMIT_WINDOW <= 3600:
            raise ConfigurationError("RATE_LIMIT_WINDOW must be between 1 and 3600 seconds")
    
    def _create_directories(self) -> None:
        """Create required directories if they don't exist."""
        directories = [
            self.OUTPUT_DIR,
            self.TEMP_DIR,
            os.path.dirname(self.DATABASE_PATH) if os.path.dirname(self.DATABASE_PATH) else '.'
        ]
        
        for directory in directories:
            if directory and directory != '.':
                try:
                    Path(directory).mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    raise ConfigurationError(
                        f"Permission denied creating directory: {directory}"
                    )
                except OSError as e:
                    raise ConfigurationError(
                        f"Error creating directory {directory}: {e}"
                    )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary (excluding sensitive values).
        
        Returns:
            Dictionary of configuration values
        """
        return {
            'elevenlabs_voice_id': self.ELEVENLABS_VOICE_ID,
            'elevenlabs_model': self.ELEVENLABS_MODEL,
            'elevenlabs_stability': self.ELEVENLABS_STABILITY,
            'elevenlabs_similarity_boost': self.ELEVENLABS_SIMILARITY_BOOST,
            'database_path': self.DATABASE_PATH,
            'log_level': self.LOG_LEVEL,
            'max_video_duration': self.MAX_VIDEO_DURATION,
            'max_video_size_mb': self.MAX_VIDEO_SIZE_MB,
            'default_video_width': self.DEFAULT_VIDEO_WIDTH,
            'default_video_height': self.DEFAULT_VIDEO_HEIGHT,
            'default_fps': self.DEFAULT_FPS,
            'output_dir': self.OUTPUT_DIR,
            'temp_dir': self.TEMP_DIR,
            'pixabay_safe_search': self.PIXABAY_SAFE_SEARCH,
            'pixabay_video_quality': self.PIXABAY_VIDEO_QUALITY,
            'pixabay_max_results': self.PIXABAY_MAX_RESULTS,
            'deepseek_model': self.DEEPSEEK_MODEL,
            'deepseek_temperature': self.DEEPSEEK_TEMPERATURE,
            'deepseek_max_tokens': self.DEEPSEEK_MAX_TOKENS,
            'max_chat_history': self.MAX_CHAT_HISTORY,
            'chat_history_expiry_days': self.CHAT_HISTORY_EXPIRY_DAYS,
            'rate_limit_requests': self.RATE_LIMIT_REQUESTS,
            'rate_limit_window': self.RATE_LIMIT_WINDOW,
        }
    
    def __repr__(self) -> str:
        """String representation of configuration."""
        return (
            f"Config(DEEPSEEK_API_KEY={'***' if self.DEEPSEEK_API_KEY else None}, "
            f"PIXABAY_API_KEY={'***' if self.PIXABAY_API_KEY else None}, "
            f"ELEVENLABS_API_KEY={'***' if self.ELEVENLABS_API_KEY else None})"
        )


# Create global configuration instance
try:
    config = Config()
except ConfigurationError as e:
    print(f"Configuration Error: {e}", file=sys.stderr)
    sys.exit(1)


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    Returns:
        Config instance
    """
    return config


def validate_api_keys() -> bool:
    """
    Validate that all required API keys are set.
    
    Returns:
        True if all keys are set, False otherwise
    """
    return all([
        config.DEEPSEEK_API_KEY,
        config.PIXABAY_API_KEY,
        config.ELEVENLABS_API_KEY
    ])


if __name__ == "__main__":
    # Test configuration loading
    print("Testing configuration...")
    try:
        test_config = Config()
        print("✓ Configuration loaded successfully")
        print(f"  Database: {test_config.DATABASE_PATH}")
        print(f"  Log Level: {test_config.LOG_LEVEL}")
        print(f"  Output Dir: {test_config.OUTPUT_DIR}")
        print(f"  Temp Dir: {test_config.TEMP_DIR}")
        print(f"  DeepSeek Model: {test_config.DEEPSEEK_MODEL}")
        print(f"  ElevenLabs Voice: {test_config.ELEVENLAB