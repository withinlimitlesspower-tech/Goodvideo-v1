```python
"""
Video Generator Module - Handles video creation logic combining media assets,
voiceover audio, and text overlays using FFmpeg.

This module provides the core video assembly functionality for the AI Video Generator,
managing the composition of background media, synchronized voiceover, and animated
text overlays into final video output.
"""

import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Configure logging
logger = logging.getLogger(__name__)


class VideoFormat(Enum):
    """Supported video output formats."""
    MP4 = "mp4"
    WEBM = "webm"
    AVI = "avi"
    MOV = "mov"


class TextPosition(Enum):
    """Text overlay positioning options."""
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER = "center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


@dataclass
class TextOverlay:
    """Configuration for a text overlay on the video."""
    text: str
    position: TextPosition = TextPosition.BOTTOM_CENTER
    font_size: int = 48
    font_color: str = "white"
    font_path: Optional[str] = None
    background_color: Optional[str] = "rgba(0,0,0,0.5)"
    animation: Optional[str] = "fade_in"  # fade_in, slide_up, none
    start_time: float = 0.0
    duration: float = 5.0


@dataclass
class MediaAsset:
    """Represents a media asset (video or image) for the composition."""
    file_path: str
    start_time: float = 0.0
    duration: Optional[float] = None
    volume: float = 1.0
    crop: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height
    scale: Optional[Tuple[int, int]] = None  # width, height


@dataclass
class VideoConfig:
    """Configuration parameters for video generation."""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    output_format: VideoFormat = VideoFormat.MP4
    codec: str = "libx264"
    audio_codec: str = "aac"
    bitrate: str = "10M"
    quality: int = 23  # CRF value (lower = better quality)
    preset: str = "medium"  # ultrafast, fast, medium, slow, veryslow


@dataclass
class VideoProject:
    """Complete video project definition."""
    media_assets: List[MediaAsset] = field(default_factory=list)
    text_overlays: List[TextOverlay] = field(default_factory=list)
    voiceover_path: Optional[str] = None
    background_music_path: Optional[str] = None
    background_music_volume: float = 0.3
    config: VideoConfig = field(default_factory=VideoConfig)
    output_path: str = "output.mp4"


class VideoGeneratorError(Exception):
    """Custom exception for video generation errors."""
    pass


class VideoGenerator:
    """
    Handles the complete video generation pipeline including media composition,
    text overlay rendering, audio mixing, and final encoding using FFmpeg.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """
        Initialize the video generator with FFmpeg paths.

        Args:
            ffmpeg_path: Path to FFmpeg executable
            ffprobe_path: Path to FFprobe executable

        Raises:
            VideoGeneratorError: If FFmpeg is not found or not executable
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._validate_ffmpeg()

    def _validate_ffmpeg(self) -> None:
        """Validate that FFmpeg and FFprobe are available."""
        for cmd, name in [(self.ffmpeg_path, "FFmpeg"), (self.ffprobe_path, "FFprobe")]:
            try:
                subprocess.run(
                    [cmd, "-version"],
                    capture_output=True,
                    check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise VideoGeneratorError(
                    f"{name} not found at '{cmd}'. Please install FFmpeg and ensure it's in PATH."
                )

    def _get_media_duration(self, file_path: str) -> float:
        """
        Get the duration of a media file using FFprobe.

        Args:
            file_path: Path to the media file

        Returns:
            Duration in seconds

        Raises:
            VideoGeneratorError: If unable to get duration
        """
        try:
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            raise VideoGeneratorError(f"Failed to get duration for {file_path}: {e}")

    def _get_media_dimensions(self, file_path: str) -> Tuple[int, int]:
        """
        Get the dimensions of a media file.

        Args:
            file_path: Path to the media file

        Returns:
            Tuple of (width, height)
        """
        try:
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0",
                    file_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            parts = result.stdout.strip().split("x")
            return int(parts[0]), int(parts[1])
        except (subprocess.CalledProcessError, ValueError, IndexError) as e:
            raise VideoGeneratorError(f"Failed to get dimensions for {file_path}: {e}")

    def _create_text_overlay_image(
        self,
        overlay: TextOverlay,
        frame_size: Tuple[int, int]
    ) -> str:
        """
        Create a temporary image file with text overlay for compositing.

        Args:
            overlay: Text overlay configuration
            frame_size: Tuple of (width, height) for the video frame

        Returns:
            Path to the generated text overlay image

        Raises:
            VideoGeneratorError: If text rendering fails
        """
        width, height = frame_size
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load font
        try:
            if overlay.font_path and os.path.exists(overlay.font_path):
                font = ImageFont.truetype(overlay.font_path, overlay.font_size)
            else:
                # Try to use a default system font
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                    "C:\\Windows\\Fonts\\arial.ttf",
                ]
                font = None
                for fp in font_paths:
                    if os.path.exists(fp):
                        font = ImageFont.truetype(fp, overlay.font_size)
                        break
                if font is None:
                    font = ImageFont.load_default()
        except Exception as e:
            logger.warning(f"Failed to load font, using default: {e}")
            font = ImageFont.load_default()

        # Calculate text bounding box
        bbox = draw.textbbox((0, 0), overlay.text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Calculate position
        padding = 20
        position_map = {
            TextPosition.TOP_LEFT: (padding, padding),
            TextPosition.TOP_CENTER: ((width - text_width) // 2, padding),
            TextPosition.TOP_RIGHT: (width - text_width - padding, padding),
            TextPosition.CENTER: ((width - text_width) // 2, (height - text_height) // 2),
            TextPosition.BOTTOM_LEFT: (padding, height - text_height - padding),
            TextPosition.BOTTOM_CENTER: ((width - text_width) // 2, height - text_height - padding),
            TextPosition.BOTTOM_RIGHT: (width - text_width - padding, height - text_height - padding),
        }
        text_x, text_y = position_map[overlay.position]

        # Draw background if specified
        if overlay.background_color:
            bg_padding = 10
            bg_bbox = (
                text_x - bg_padding,
                text_y - bg_padding,
                text_x + text_width + bg_padding,
                text_y + text_height + bg_padding
            )
            draw.rectangle(bg_bbox, fill=overlay.background_color)

        # Draw text
        draw.text((text_x, text_y), overlay.text, fill=overlay.font_color, font=font)

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp_file.name, "PNG")
        logger.debug(f"Created text overlay image: {temp_file.name}")
        return temp_file.name

    def _build_complex_filter(
        self,
        project: VideoProject,
        text_overlay_paths: List[Tuple[str, TextOverlay]]
    ) -> str:
        """
        Build the FFmpeg complex filter graph for video composition.

        Args:
            project: Video project configuration
            text_overlay_paths: List of (image_path, overlay_config) tuples

        Returns:
            FFmpeg complex filter string
        """
        filters = []
        input_count = 0
        current_label = "0:v"  # Start with first video input

        # Process media assets
        for i, asset in enumerate(project.media_assets):
            if i == 0:
                # First video input - apply scaling and padding
                scale_filter = (
                    f"[0:v]scale={project.config.width}:{project.config.height}:"
                    f"force_original_aspect_ratio=decrease,"
                    f"pad={project.config.width}:{project.config.height}:"
                    f"(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
                )
                filters.append(scale_filter)
                current_label = f"[v{i}]"
            else:
                # Subsequent videos - concatenate or overlay
                scale_filter = (
                    f"[{i}:v]scale={project.config.width}:{project.config.height}:"
                    f"force_original_aspect_ratio=decrease,"
                    f"pad={project.config.width}:{project.config.height}:"
                    f"(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
                )
                filters.append(scale_filter)
                # Concatenate video streams
                concat_filter = f"{current_label}[v{i}]concat=n={i+1}:v=1:a=0[vc]"
                filters.append(concat_filter)
                current_label = "[vc]"

        # Add text overlays
        for idx, (text_path, overlay) in enumerate(text_overlay_paths):
            text_input_label = f"[{len(project.media_assets) + idx}:v]"
            overlay_filter = (
                f"{current_label}{text_input_label}overlay="
                f"enable='between(t,{overlay.start_time},{overlay.start_time + overlay.duration})'"
                f"[v_text{idx}]"
            )
            filters.append(overlay_filter)
            current_label = f"[v_text{idx}]"

        # Final output label
        final_filter = f"{current_label}format=yuv420p[vout]"
        filters.append(final_filter)

        return ";".join(filters)

    def _generate_ffmpeg_command(
        self,
        project: VideoProject,
        text_overlay_paths: List[Tuple[str, TextOverlay]]
    ) -> List[str]:
        """
        Generate the complete FFmpeg command for video assembly.

        Args:
            project: Video project configuration
            text_overlay_paths: List of (image_path, overlay_config) tuples

        Returns:
            List of command arguments for subprocess
        """
        cmd = [self.ffmpeg_path, "-y"]  # Overwrite output file

        # Add input files
        for asset in project.media_assets:
            if not os.path.exists(asset.file_path):
                raise VideoGeneratorError(f"Media file not found: {asset.file_path}")
            cmd.extend(["-i", asset.file_path])

        # Add text overlay images as inputs
        for text_path, _ in text_overlay_paths:
            cmd.extend(["-i", text_path])

        # Add voiceover if provided
        if project.voiceover_path and os.path.exists(project.voiceover_path):
            cmd.extend(["-i", project.voiceover_path])

        # Add background music if provided
        if project.background_music_path and os.path.exists(project.background_music_path):
            cmd.extend(["-i", project.background_music_path])

        # Build filter complex
        filter_complex = self._build_complex_filter(project, text_overlay_paths)
        cmd.extend(["-filter_complex", filter_complex])

        # Audio handling
        audio_inputs = []
        if project.voiceover_path:
            audio_inputs.append(f"[{len(project.media_assets) + len(text_overlay_paths)}:a]")
        if project.background_music_path:
            music_idx = len(project.media_assets) + len(text_overlay_paths) + (1 if project.voiceover_path else 0)
            audio_inputs.append(f"[{music_idx}:a]")

        if audio_inputs:
            audio_filter_parts = []
            if len(audio_inputs) == 2:
                audio_filter = (
                    f"{audio_inputs[0]}volume=1.0[a_voice];"
                    f"{audio_inputs[1]}volume={project.background_music_volume}[a_music];"
                    f"[a_voice][a_music]amix=inputs=2:duration=first[aout]"
                )
                cmd.extend(["-filter_complex", audio_filter])
                cmd.extend(["-map", "[aout]"])
            else:
                cmd.extend(["-map", audio_inputs[0].rstrip(":a") + ":a"])

        # Map video output
        cmd.extend(["-map", "[vout]"])

        # Output encoding settings
        cmd.extend([
            "-c:v", project.config.codec,
            "-preset", project.config.preset,
            "-crf", str(project.config.quality),
            "-b:v", project.config.bitrate,
            "-r", str(project.config.fps),
            "-pix_fmt", "yuv420p",
        ])

        # Audio encoding settings
        if audio_inputs:
            cmd.extend([
                "-c:a", project.config.audio_codec,
                "-b:a", "192k",
                "-ar", "44100",
            ])
        else:
            cmd.extend(["-an"])

        # Output file
        cmd.append(project.output_path)

        logger.debug(f"Generated FFmpeg command: {' '.join(cmd)}")
        return cmd

    def generate_video(self, project: VideoProject) -> str:
        """
        Generate a complete video from the project configuration.

        Args:
            project: VideoProject with all media, text, and audio configurations

        Returns:
            Path to the generated video file

        Raises:
            VideoGeneratorError: If video generation fails
        """
        logger.info(f"Starting video generation: {project.output_path}")

        # Validate project
        if not project.media_assets:
            raise VideoGeneratorError("No media assets provided for video generation")

        # Create output directory if needed
        output_dir = os.path.dirname(project.output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Generate text overlay images
        text_overlay_paths = []
        try:
            for overlay in project.text_overlays:
                text_path = self._create_text_overlay_image(
                    overlay,
                    (project.config.width, project.config.height)
                )
                text_overlay_paths.append((text_path, overlay))

            # Generate FFmpeg command
            cmd = self._generate_ffmpeg_command(project, text_overlay_paths)

            # Execute FFmpeg
            logger.info("Executing FFmpeg video assembly...")
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            if process.returncode != 0:
                raise VideoGeneratorError(
                    f"FFmpeg failed with error:\n{process.stderr}"
                )

            logger.info(f"Video generated successfully: {project.output_path}")
            return project.output_path

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg process failed: {e.stderr if e.stderr else str(e)}"
            logger.error(error_msg)
            raise VideoGeneratorError(error_msg)
        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            raise VideoGeneratorError(f"Video generation failed: {e}")
        finally:
            # Clean up temporary text overlay images