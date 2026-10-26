"""Draw annotation shapes from agents as the PNG drawing the review player shows."""
from __future__ import annotations

import base64
import math
from io import BytesIO
from typing import Annotated, Literal, Optional

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, model_validator

# The browser drawing is the size of the shown frame; the player stretches it
# over the frame, so only the aspect ratio must match the media.
DRAWING_LONG_SIDE = 1280
SUPERSAMPLE = 2
DEFAULT_COLOR = '#ff3b30'  # The first pen color in the review player.
DEFAULT_WIDTH = 4  # The review player's pen width.

Coordinate = Annotated[float, Field(ge=0, le=1)]
_POINTS = ('x1', 'y1', 'x2', 'y2')
_REQUIRED = {
    'arrow': _POINTS,
    'line': _POINTS,
    'rect': _POINTS,
    'ellipse': _POINTS,
    'freehand': ('points',),
    'text': ('x', 'y', 'text'),
}


class AnnotationShape(BaseModel):
    """One mark on the frame. Coordinates are fractions of the frame: 0,0 is the top left corner, 1,1 the bottom right."""

    type: Literal['arrow', 'line', 'rect', 'ellipse', 'freehand', 'text'] = Field(
        description='arrow, line, rect and ellipse use x1,y1,x2,y2. freehand uses points. text uses x,y and text.',
    )
    x1: Optional[Coordinate] = Field(None, description='Start of an arrow or line, or one corner of the box of a rect or ellipse.')
    y1: Optional[Coordinate] = None
    x2: Optional[Coordinate] = Field(None, description='End of a line, the point of an arrow, or the opposite corner of the box.')
    y2: Optional[Coordinate] = None
    points: Optional[list[tuple[Coordinate, Coordinate]]] = Field(
        None, min_length=2, max_length=2000, description='freehand: the path as [x, y] pairs, in order.',
    )
    x: Optional[Coordinate] = Field(None, description='text: the left edge of the text.')
    y: Optional[Coordinate] = Field(None, description='text: the top edge of the text.')
    text: Optional[str] = Field(None, min_length=1, max_length=200, description='text: the words to write on the frame.')
    color: str = Field(DEFAULT_COLOR, pattern=r'^#[0-9a-fA-F]{6}$', description='Hex color, such as #ff3b30 (red, the default) or #ffcc00 (yellow).')
    width: float = Field(DEFAULT_WIDTH, ge=1, le=40, description='Line width in pixels on a drawing 1280 pixels on its long side. The default 4 is the pen width in the app.')

    @model_validator(mode='after')
    def _require_type_fields(self):
        missing = [name for name in _REQUIRED[self.type] if getattr(self, name) is None]
        if missing:
            raise ValueError(f'The {self.type} shape needs {", ".join(missing)}.')
        return self


def drawing_size(frame_size: tuple[int, int]) -> tuple[int, int]:
    width, height = frame_size
    if width >= height:
        return DRAWING_LONG_SIDE, max(1, round(DRAWING_LONG_SIDE * height / width))
    return max(1, round(DRAWING_LONG_SIDE * width / height)), DRAWING_LONG_SIDE


def _round_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: str, width: float) -> None:
    # Round ends and joins, as the browser pen draws.
    draw.line(points, fill=color, width=max(1, round(width)), joint='curve')
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], tip: tuple[float, float], color: str, width: float, scale: int) -> None:
    length = math.dist(start, tip)
    head = min(max(width * 5, 24 * scale), length * 0.6) if length else 0
    if not head:
        return
    ux, uy = (tip[0] - start[0]) / length, (tip[1] - start[1]) / length
    base = (tip[0] - ux * head * 0.8, tip[1] - uy * head * 0.8)
    _round_line(draw, [start, base], color, width)
    back = (tip[0] - ux * head, tip[1] - uy * head)
    side = (-uy * head * 0.55, ux * head * 0.55)
    draw.polygon([tip, (back[0] + side[0], back[1] + side[1]), (back[0] - side[0], back[1] - side[1])], fill=color)


def _draw_text(draw: ImageDraw.ImageDraw, shape: AnnotationShape, size: tuple[int, int], scale: int) -> None:
    font_size = max(12 * scale, round(min(size) / 16))
    font = ImageFont.load_default(size=font_size)
    stroke = max(1, font_size // 12)
    left, top, right, bottom = draw.multiline_textbbox((0, 0), shape.text, font=font, stroke_width=stroke)
    # Keep the words on the frame when the position is near an edge.
    x = min(shape.x * size[0], size[0] - (right - left)) - left
    y = min(shape.y * size[1], size[1] - (bottom - top)) - top
    draw.multiline_text((max(-left, x), max(-top, y)), shape.text, fill=shape.color, font=font, stroke_width=stroke, stroke_fill='#000000')


def render_annotation_shapes(shapes: list[AnnotationShape], frame_size: tuple[int, int]) -> str:
    """Return the shapes as a transparent PNG data URL with the aspect ratio of the frame."""
    width, height = drawing_size(frame_size)
    size = (width * SUPERSAMPLE, height * SUPERSAMPLE)
    # Draw large and reduce, for smooth edges.
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        stroke = shape.width * SUPERSAMPLE
        if shape.type == 'text':
            _draw_text(draw, shape, size, SUPERSAMPLE)
            continue
        if shape.type == 'freehand':
            _round_line(draw, [(x * size[0], y * size[1]) for x, y in shape.points], shape.color, stroke)
            continue
        start = (shape.x1 * size[0], shape.y1 * size[1])
        end = (shape.x2 * size[0], shape.y2 * size[1])
        if shape.type == 'line':
            _round_line(draw, [start, end], shape.color, stroke)
        elif shape.type == 'arrow':
            _draw_arrow(draw, start, end, shape.color, stroke, SUPERSAMPLE)
        else:
            box = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
            draw_box = draw.rectangle if shape.type == 'rect' else draw.ellipse
            draw_box(box, outline=shape.color, width=max(1, round(stroke)))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
