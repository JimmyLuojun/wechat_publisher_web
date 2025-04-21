# /Users/junluo/Documents/wechat_publisher_web/publishing_engine/utils/image_processing.py

import logging
from pathlib import Path
from PIL import Image
import io
import os

logger = logging.getLogger(__name__)

# Define constants for WeChat limits (KB)
# WeChat Official Account Limits: Thumb=64KB, Content Image=1MB (some docs say 2MB, but 1MB is safer)
COVER_IMAGE_SIZE_LIMIT_KB = 64
CONTENT_IMAGE_SIZE_LIMIT_KB = 1024 # 1 MB = 1024 KB

# Default quality settings for optimization
DEFAULT_JPEG_QUALITY = 85
MIN_JPEG_QUALITY = 60
QUALITY_STEP = 5

def ensure_image_size(
    image_path: Path,
    size_limit_kb: int,
    quality: int = DEFAULT_JPEG_QUALITY,
    min_quality: int = MIN_JPEG_QUALITY,
    step: int = QUALITY_STEP
) -> Path:
    """
    Checks if an image exceeds a size limit and optimizes it if necessary.
    Attempts reducing JPEG quality first, then resizing if needed.
    Returns the path to the processed image (original or a new optimized file).

    Args:
        image_path: Path to the input image.
        size_limit_kb: The maximum allowed size in kilobytes.
        quality: Initial JPEG quality target.
        min_quality: The minimum JPEG quality to attempt.
        step: How much to decrease quality by each iteration for JPEGs.

    Returns:
        Path to the image file that meets the size requirement.

    Raises:
        FileNotFoundError: If the input image_path doesn't exist.
        ValueError: If the image cannot be processed or size reduction fails.
        ImportError: If Pillow is not installed.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found at: {image_path}")

    size_limit_bytes = size_limit_kb * 1024
    original_size = image_path.stat().st_size

    if original_size <= size_limit_bytes:
        logger.debug(f"Image '{image_path.name}' ({original_size / 1024:.1f} KB) is within limit ({size_limit_kb} KB).")
        return image_path

    logger.info(f"Image '{image_path.name}' ({original_size / 1024:.1f} KB) exceeds limit ({size_limit_kb} KB). Attempting optimization...")

    try:
        img = Image.open(image_path)
        # Preserve original format if known, default to JPEG otherwise
        img_format = img.format if img.format else 'JPEG'
        output_suffix = image_path.suffix.lower()

        # Ensure image mode is compatible (convert indexed/etc. to RGB/RGBA)
        if img.mode == 'P': # Indexed color
             img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
             logger.debug(f"Converted indexed image '{image_path.name}' mode to {img.mode}.")
             # Decide output format after conversion (PNG preserves transparency)
             img_format = 'PNG' if img.mode == 'RGBA' else 'JPEG'
             output_suffix = '.png' if img.mode == 'RGBA' else '.jpg'
        elif img.mode not in ('RGB', 'RGBA', 'L'): # L = Grayscale
             img = img.convert('RGB')
             logger.debug(f"Converted image '{image_path.name}' mode '{img.mode}' to RGB.")
             img_format = 'JPEG'
             output_suffix = '.jpg'

        # Define output path (add suffix like _optimized before extension)
        output_filename = f"{image_path.stem}_optimized{output_suffix}"
        output_path = image_path.with_name(output_filename)

        current_quality = quality
        saved = False
        buffer = io.BytesIO()

        # --- Optimization Strategy ---

        # 1. Try saving with current settings (or reduced quality for JPEG)
        is_jpeg = img_format.upper() in ['JPEG', 'JPG']
        if is_jpeg:
            logger.debug(f"Attempting JPEG quality reduction for '{image_path.name}'. Start quality: {current_quality}")
            while current_quality >= min_quality:
                buffer.seek(0)
                buffer.truncate(0)
                img.save(buffer, format='JPEG', quality=current_quality, optimize=True)
                buffer_size = buffer.tell()
                if buffer_size <= size_limit_bytes:
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    logger.info(f"Optimized '{image_path.name}' via quality ({current_quality}) to {buffer_size / 1024:.1f} KB -> '{output_path.name}'.")
                    saved = True
                    break
                logger.debug(f"Quality {current_quality} still too large ({buffer_size / 1024:.1f} KB).")
                current_quality -= step
            if saved: return output_path

        # 2. If still too large (or not JPEG), try resizing
        if not saved:
            logger.debug(f"Quality reduction insufficient or not applicable. Attempting resize for '{image_path.name}'.")
            original_width, original_height = img.size
            scale_factor = (size_limit_bytes / original_size) ** 0.5  # Estimate scale based on size ratio sqrt
            scale_factor = min(scale_factor, 0.95) # Don't start too aggressively, ensure some reduction

            while scale_factor > 0.1: # Safety net to avoid excessive shrinking
                new_width = max(1, int(original_width * scale_factor))
                new_height = max(1, int(original_height * scale_factor))
                logger.debug(f"Resizing '{image_path.name}' to {new_width}x{new_height} (scale: {scale_factor:.2f})")
                try:
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                except ValueError as resize_err:
                    logger.error(f"Error during resize attempt: {resize_err}")
                    break # Stop if resize fails

                buffer.seek(0)
                buffer.truncate(0)
                save_format = 'PNG' if img_format.upper() == 'PNG' else 'JPEG'
                save_params = {'optimize': True}
                if save_format == 'JPEG':
                    save_params['quality'] = quality # Use target quality after resize

                resized_img.save(buffer, format=save_format, **save_params)
                buffer_size = buffer.tell()

                if buffer_size <= size_limit_bytes:
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    logger.info(f"Resized and saved '{image_path.name}' to {buffer_size / 1024:.1f} KB ({new_width}x{new_height}) -> '{output_path.name}'.")
                    saved = True
                    break
                else:
                    logger.debug(f"Resized image still too large ({buffer_size / 1024:.1f} KB). Reducing scale factor.")
                    scale_factor *= 0.9 # Reduce scale further for next attempt

        if not saved:
            # Last resort: Save JPEG at minimum quality without resizing (if applicable)
            if is_jpeg and current_quality < min_quality: # Only if quality reduction was attempted
                logger.warning(f"Resize failed or insufficient for '{image_path.name}'. Trying final save at min quality {min_quality}.")
                buffer.seek(0)
                buffer.truncate(0)
                img.save(buffer, format='JPEG', quality=min_quality, optimize=True)
                buffer_size = buffer.tell()
                if buffer_size <= size_limit_bytes:
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    logger.info(f"Saved '{image_path.name}' at min quality ({min_quality}) to {buffer_size / 1024:.1f} KB -> '{output_path.name}'.")
                    saved = True
                    return output_path

        if not saved:
            raise ValueError(f"Failed to reduce image '{image_path.name}' size below {size_limit_kb} KB after multiple attempts.")

        return output_path

    except FileNotFoundError:
        raise # Re-raise specific error
    except ImportError:
        logger.critical("Pillow library is not installed. Please install it: pip install Pillow")
        raise ImportError("Pillow library is required for image processing.")
    except Exception as e:
        logger.exception(f"Error processing image '{image_path.name}': {e}")
        # Include original image path in error for context
        raise ValueError(f"Failed to process image '{image_path.name}': {e}") from e