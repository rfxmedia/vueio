"""Bounded validation of standalone 3D Cube LUTs; matches the viewer parser."""

import io
import math
import re
import struct


MAX_LUT_BYTES = 32 * 1024 * 1024
MAX_LIBRARY_COUNT = 64
MAX_LIBRARY_BYTES = 256 * 1024 * 1024
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
HEADERS = {'TITLE', 'LUT_3D_SIZE', 'DOMAIN_MIN', 'DOMAIN_MAX', 'LUT_3D_INPUT_RANGE'}


def validate_cube(text: str, filename: str) -> tuple[str, int]:
    if '\x00' in text:
        raise ValueError('The LUT must contain text without null bytes.')
    name = re.split(r'[/\\]', filename)[-1]
    name = re.sub(r'\.cube$', '', name, flags=re.IGNORECASE) or 'Custom LUT'
    size = rows = 0
    seen = set()
    domain_min, domain_max = [0.0] * 3, [1.0] * 3
    line_number = 0

    def fail(message):
        raise ValueError(f'Line {line_number}: {message}')

    def float32(value):
        try:
            result = struct.unpack('f', struct.pack('f', value))[0]
        except (OverflowError, struct.error):
            fail('Numbers must fit within the finite 32-bit float range.')
        if not math.isfinite(result):
            fail('Numbers must fit within the finite 32-bit float range.')
        return result

    def number(token):
        if not NUMBER.fullmatch(token):
            fail('Expected finite decimal numbers.')
        return float32(float(token))

    # StringIO handles CR, LF and CRLF without allocating an array of all rows.
    for line_number, raw in enumerate(io.StringIO(text, newline=None), 1):
        raw = raw.strip().strip('\ufeff').strip()
        if not raw or raw.startswith('#'):
            continue
        line = raw if re.match(r'TITLE(?:\s|$)', raw) else raw.split('#', 1)[0].strip()
        tokens = line.split(None, 4)
        keyword = tokens[0]
        if keyword.startswith('LUT_1D_'):
            fail('1D LUTs and combined shapers are not supported. Export a standalone 3D .cube LUT.')
        if keyword in HEADERS:
            if rows:
                fail('LUT headers must appear before the sample rows.')
            if keyword in seen:
                fail(f'{keyword} must appear only once.')
            seen.add(keyword)
            if keyword == 'TITLE':
                title = re.fullmatch(r'TITLE\s+"([^"]*)"\s*(?:#.*)?', line)
                if not title:
                    fail('TITLE must contain one quoted name.')
                name = title[1].strip() or name
            elif keyword == 'LUT_3D_SIZE':
                if len(tokens) != 2 or not re.fullmatch(r'[0-9]+', tokens[1]):
                    fail('LUT_3D_SIZE must be an integer from 2 to 65.')
                candidate_size = float(tokens[1])
                if not 2 <= candidate_size <= 65:
                    fail('Supported 3D LUT sizes are 2 through 65.')
                size = int(candidate_size)
            elif keyword == 'LUT_3D_INPUT_RANGE':
                if seen & {'DOMAIN_MIN', 'DOMAIN_MAX'}:
                    fail('Use either LUT_3D_INPUT_RANGE or DOMAIN_MIN/DOMAIN_MAX, not both.')
                if len(tokens) != 3:
                    fail('LUT_3D_INPUT_RANGE requires a minimum and maximum.')
                domain_min, domain_max = [number(tokens[1])] * 3, [number(tokens[2])] * 3
            else:
                if 'LUT_3D_INPUT_RANGE' in seen:
                    fail('Use either LUT_3D_INPUT_RANGE or DOMAIN_MIN/DOMAIN_MAX, not both.')
                if len(tokens) != 4:
                    fail(f'{keyword} requires three numbers.')
                values = [number(token) for token in tokens[1:]]
                if keyword == 'DOMAIN_MIN':
                    domain_min = values
                else:
                    domain_max = values
            continue
        if re.match(r'[A-Za-z_]', keyword):
            fail(f'Unsupported .cube directive: {keyword[:60]}.')
        if not size:
            fail('LUT_3D_SIZE must appear before the sample rows.')
        if len(tokens) != 3:
            fail('Each sample row must contain exactly three numbers.')
        if rows >= size ** 3:
            fail(f'The LUT contains more than the expected {size ** 3} sample rows.')
        for token in tokens:
            number(token)
        rows += 1
    if not size:
        raise ValueError('Select a standalone 3D .cube LUT with LUT_3D_SIZE.')
    if rows != size ** 3:
        raise ValueError(f'Expected {size ** 3} sample rows; found {rows}.')
    if any(float32(high - low) <= 0 for low, high in zip(domain_min, domain_max)):
        raise ValueError('Each input domain must have a minimum below its maximum and a finite 32-bit span.')
    return name[:200], size
