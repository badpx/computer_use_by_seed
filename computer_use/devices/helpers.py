"""Helpers for working with device frames."""

from __future__ import annotations

import base64
import io
from typing import Optional

from .base import DeviceFrame

SUPPORTED_MIME_TYPES = {'image/png', 'image/jpeg'}


def validate_frame_mime_type(mime_type: str) -> str:
    normalized = str(mime_type or '').strip().lower()
    if normalized not in SUPPORTED_MIME_TYPES:
        raise ValueError(f'不支持的截图 MIME 类型: {mime_type}')
    return normalized


def extract_frame_mime_type(frame: DeviceFrame) -> str:
    mime_type, _ = _split_data_url(frame.image_data_url)
    return validate_frame_mime_type(mime_type)


def extract_frame_base64(frame: DeviceFrame) -> str:
    _, image_base64 = _split_data_url(frame.image_data_url)
    return image_base64


def frame_to_data_url(frame: DeviceFrame) -> str:
    mime_type = extract_frame_mime_type(frame)
    image_base64 = extract_frame_base64(frame)
    return f'data:{mime_type};base64,{image_base64}'


def prepare_model_frame(
    frame: DeviceFrame,
    screenshot_size: Optional[int] = None,
) -> DeviceFrame:
    extract_frame_mime_type(frame)
    if screenshot_size is None:
        return frame
    if screenshot_size <= 0:
        return frame
    if frame.width == screenshot_size and frame.height == screenshot_size:
        return frame
    return _resize_frame(frame, screenshot_size)


def frame_to_bytes(frame: DeviceFrame) -> bytes:
    return base64.b64decode(extract_frame_base64(frame).encode('utf-8'))


def detect_frame_size(frame: DeviceFrame) -> tuple[int, int]:
    return detect_image_size(
        frame_to_bytes(frame),
        mime_type=extract_frame_mime_type(frame),
    )


def detect_image_size(
    image_bytes: bytes,
    mime_type: Optional[str] = None,
) -> tuple[int, int]:
    normalized_mime = None
    if mime_type:
        try:
            normalized_mime = validate_frame_mime_type(mime_type)
        except ValueError:
            normalized_mime = None

    detectors = []
    if normalized_mime == 'image/png':
        detectors = [_detect_png_size, _detect_jpeg_size]
    elif normalized_mime == 'image/jpeg':
        detectors = [_detect_jpeg_size, _detect_png_size]
    else:
        detectors = [_detect_png_size, _detect_jpeg_size]

    for detector in detectors:
        size = detector(image_bytes)
        if size is not None:
            return size

    size = _detect_image_size_with_pillow(image_bytes)
    if size is not None:
        return size

    raise RuntimeError('无法从图片数据中解析宽高')


def load_frame_image(frame: DeviceFrame):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('处理远端截图需要安装 Pillow') from exc

    return Image.open(io.BytesIO(frame_to_bytes(frame)))


def save_frame(frame: DeviceFrame, path: str) -> None:
    with open(path, 'wb') as file_obj:
        file_obj.write(frame_to_bytes(frame))


def _resize_frame(frame: DeviceFrame, screenshot_size: int) -> DeviceFrame:
    image = load_frame_image(frame)
    resized = image.resize((screenshot_size, screenshot_size), _get_resize_resample())
    mime_type = extract_frame_mime_type(frame)
    target_format = 'PNG' if mime_type == 'image/png' else 'JPEG'
    buffer = io.BytesIO()
    metadata = dict(frame.metadata)
    try:
        save_kwargs = {'format': target_format}
        if target_format == 'JPEG' and resized.mode not in ('RGB', 'L'):
            resized = resized.convert('RGB')
        resized.save(buffer, **save_kwargs)
    except Exception:
        buffer = io.BytesIO()
        resized.save(buffer, format='PNG')
        mime_type = 'image/png'
        metadata['transcoded'] = True
    return DeviceFrame(
        image_data_url=(
            f"data:{mime_type};base64,"
            f"{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
        ),
        width=screenshot_size,
        height=screenshot_size,
        metadata=metadata,
    )


def _detect_png_size(image_bytes: bytes) -> Optional[tuple[int, int]]:
    if len(image_bytes) < 24:
        return None
    signature = b'\x89PNG\r\n\x1a\n'
    if not image_bytes.startswith(signature):
        return None
    width = int.from_bytes(image_bytes[16:20], 'big')
    height = int.from_bytes(image_bytes[20:24], 'big')
    if width <= 0 or height <= 0:
        return None
    return width, height


def _detect_jpeg_size(image_bytes: bytes) -> Optional[tuple[int, int]]:
    if len(image_bytes) < 4 or not image_bytes.startswith(b'\xff\xd8'):
        return None

    offset = 2
    size = len(image_bytes)
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3,
        0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB,
        0xCD, 0xCE, 0xCF,
    }

    while offset + 1 < size:
        marker_offset = image_bytes.find(b'\xff', offset)
        if marker_offset < 0 or marker_offset + 1 >= size:
            return None

        marker_index = marker_offset + 1
        while marker_index < size and image_bytes[marker_index] == 0xFF:
            marker_index += 1
        if marker_index >= size:
            return None

        marker = image_bytes[marker_index]

        if marker == 0xDA:
            break
        if marker in {0xD8, 0xD9}:
            offset = marker_index + 1
            continue

        if marker in sof_markers:
            if marker_offset + 9 >= size:
                return None
            height = int.from_bytes(
                image_bytes[marker_offset + 5:marker_offset + 7],
                'big',
            )
            width = int.from_bytes(
                image_bytes[marker_offset + 7:marker_offset + 9],
                'big',
            )
            if width <= 0 or height <= 0:
                return None
            return width, height

        offset = marker_index + 1

    return None


def _detect_image_size_with_pillow(image_bytes: bytes) -> Optional[tuple[int, int]]:
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
    except Exception:
        return None

    if width <= 0 or height <= 0:
        return None
    return width, height


def _split_data_url(image_data_url: str) -> tuple[str, str]:
    payload = str(image_data_url or '').strip()
    prefix = 'data:'
    marker = ';base64,'
    if not payload.startswith(prefix) or marker not in payload:
        raise ValueError('截图数据不是合法的 data URL')
    mime_type, image_base64 = payload[len(prefix):].split(marker, 1)
    return mime_type.strip().lower(), image_base64.strip()


def _get_resize_resample() -> int:
    try:
        from PIL import Image as PILImage
    except ImportError:
        return 1

    resampling = getattr(PILImage, 'Resampling', None)
    if resampling is not None:
        return resampling.LANCZOS
    return PILImage.LANCZOS
