#!/usr/bin/env python3
"""
Fast vectorization using potrace + efficient gap insertion for laser cutting.

Requirements:
    pip install numpy opencv-python-headless svgpathtools
    sudo apt install potrace  # or brew install potrace on macOS

Usage:
    python vectorize_fast.py \
        --input precise_lineart.png \
        --output precise_gapped.svg \
        --gap-length 3 \
        --gap-spacing 40 \
        --stroke-width 1.0

Features:
- Uses potrace for fast, accurate vectorization
- Efficient linear-time gap insertion algorithm
- Handles complex drawings quickly
"""

import argparse
import subprocess
import tempfile
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import List, Tuple
import math

try:
    import cv2
    import numpy as np
except ImportError:
    print("Error: opencv-python not found. Install with: pip install opencv-python-headless")
    exit(1)

try:
    from svgpathtools import parse_path, Path as SvgPath, Line, CubicBezier, QuadraticBezier, Arc
except ImportError:
    print("Error: svgpathtools not found. Install with: pip install svgpathtools")
    exit(1)


def check_potrace():
    """Check if potrace is installed."""
    try:
        subprocess.run(['potrace', '--version'],
                      capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: potrace not found.")
        print("Install with:")
        print("  Ubuntu/Debian: sudo apt install potrace")
        print("  macOS: brew install potrace")
        print("  Or download from: http://potrace.sourceforge.net/")
        return False


def convert_to_pbm(input_png: str, output_pbm: str, threshold: int = 128):
    """
    Convert PNG to PBM format for potrace.
    Potrace only accepts PNM/BMP formats.
    """
    img = cv2.imread(input_png, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {input_png}")

    # Threshold to binary (black and white only)
    _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

    # Write as PBM (portable bitmap format)
    # PBM format: P4 (binary) or P1 (ASCII)
    # We'll use cv2 to write as BMP which potrace also accepts
    cv2.imwrite(output_pbm, binary)
    return output_pbm


def vectorize_with_potrace(input_png: str, output_svg: str) -> str:
    """
    Use potrace to vectorize the PNG to SVG.
    Returns path to the generated SVG.
    """
    print(f"Vectorizing {input_png} with potrace...")

    # Convert PNG to BMP format (potrace requirement)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bmp', delete=False) as tmp:
        tmp_bmp = tmp.name

    try:
        convert_to_pbm(input_png, tmp_bmp)

        # potrace parameters:
        # -s = SVG output
        # -k 0.5 = corner threshold (lower = sharper corners)
        # -t 2 = suppress speckles of this size
        # -O 1.0 = curve optimization tolerance
        cmd = [
            'potrace',
            '-s',           # SVG output
            '-k', '0.5',    # corner threshold
            '-t', '2',      # suppress small speckles
            '-O', '1.0',    # optimization tolerance
            '-o', output_svg,
            tmp_bmp
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ Vectorization complete")
        return output_svg
    except subprocess.CalledProcessError as e:
        print(f"Error running potrace: {e.stderr}")
        raise
    finally:
        # Clean up temp BMP
        if os.path.exists(tmp_bmp):
            os.unlink(tmp_bmp)


def parse_svg_paths(svg_file: str) -> Tuple[List[SvgPath], dict]:
    """
    Parse SVG and extract all path data.
    Returns list of Path objects and SVG attributes.
    """
    tree = ET.parse(svg_file)
    root = tree.getroot()

    # Extract viewBox or dimensions
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    viewbox = root.get('viewBox', '')
    width = root.get('width', '100%')
    height = root.get('height', '100%')

    svg_attrs = {
        'viewBox': viewbox,
        'width': width,
        'height': height
    }

    paths = []
    for path_elem in root.findall('.//svg:path', ns):
        d = path_elem.get('d', '')
        if d:
            try:
                path = parse_path(d)
                paths.append(path)
            except Exception as e:
                print(f"Warning: Could not parse path: {e}")

    # Also check paths without namespace
    for path_elem in root.findall('.//path'):
        d = path_elem.get('d', '')
        if d:
            try:
                path = parse_path(d)
                paths.append(path)
            except Exception as e:
                print(f"Warning: Could not parse path: {e}")

    print(f"✓ Extracted {len(paths)} paths from SVG")
    return paths, svg_attrs


def insert_gaps_in_path(path: SvgPath, gap_length: float, gap_spacing: float) -> List[SvgPath]:
    """
    Insert gaps along a path at regular intervals.

    Args:
        path: SVG path object
        gap_length: Length of each gap
        gap_spacing: Distance between gap starts

    Returns:
        List of path segments (gaps removed)
    """
    if len(path) == 0:
        return []

    total_length = path.length()
    if total_length == 0:
        return [path]

    # Calculate gap positions along the path
    gap_positions = []  # List of (gap_start, gap_end) tuples

    # If path is shorter than gap_spacing, put one gap in the middle
    if total_length < gap_spacing:
        mid = total_length / 2.0
        gap_start = max(0, mid - gap_length / 2.0)
        gap_end = min(total_length, mid + gap_length / 2.0)

        # Only add gap if it doesn't consume the entire path
        if gap_start > 0 or gap_end < total_length:
            gap_positions.append((gap_start, gap_end))
    else:
        # Place gaps at regular intervals
        pos = gap_spacing
        while pos < total_length:
            gap_start = pos
            gap_end = min(pos + gap_length, total_length)
            gap_positions.append((gap_start, gap_end))
            pos += gap_spacing

    # If no gaps, return original path
    if not gap_positions:
        return [path]

    # Build segments between gaps
    segments_out = []
    segment_start = 0.0

    for gap_start, gap_end in gap_positions:
        # Add segment before this gap
        if segment_start < gap_start:
            try:
                t_start = segment_start / total_length
                t_end = gap_start / total_length

                # Ensure valid range
                t_start = max(0.0, min(1.0, t_start))
                t_end = max(0.0, min(1.0, t_end))

                if t_end > t_start:
                    seg = path.cropped(t_start, t_end)
                    if len(seg) > 0:
                        segments_out.append(seg)
            except Exception as e:
                # Skip this segment if cropping fails
                pass

        # Move past the gap
        segment_start = gap_end

    # Add final segment after last gap
    if segment_start < total_length:
        try:
            t_start = segment_start / total_length
            t_start = max(0.0, min(1.0, t_start))

            if t_start < 1.0:
                seg = path.cropped(t_start, 1.0)
                if len(seg) > 0:
                    segments_out.append(seg)
        except Exception as e:
            # Skip if cropping fails
            pass

    return segments_out if segments_out else [path]


def path_to_svg_d(path: SvgPath) -> str:
    """Convert a Path object back to SVG d attribute string."""
    return path.d()


def write_svg_with_gaps(paths: List[SvgPath], svg_attrs: dict,
                        output_file: str, stroke_width: float = 1.0):
    """
    Write paths to SVG file with specified stroke width.
    """
    # Create SVG root
    svg_ns = "http://www.w3.org/2000/svg"
    ET.register_namespace('', svg_ns)

    # Parse viewBox to get dimensions for flipping
    viewbox = svg_attrs.get('viewBox', '0 0 1000 1000')
    viewbox_parts = viewbox.split()
    if len(viewbox_parts) == 4:
        vb_height = float(viewbox_parts[3])
    else:
        vb_height = 1000

    root = ET.Element('svg', {
        'xmlns': svg_ns,
        'viewBox': viewbox,
        'width': svg_attrs.get('width', '100%'),
        'height': svg_attrs.get('height', '100%')
    })

    # Create a group with transform to flip Y-axis
    # This corrects the upside-down output from potrace
    group = ET.SubElement(root, 'g', {
        'transform': f'scale(1,-1) translate(0,-{vb_height})'
    })

    # Add paths to the group
    for path in paths:
        if len(path) == 0:
            continue
        path_elem = ET.SubElement(group, 'path', {
            'd': path_to_svg_d(path),
            'fill': 'none',
            'stroke': 'black',
            'stroke-width': str(stroke_width),
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round'
        })

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✓ Wrote {len(paths)} gapped paths to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Fast vectorization with potrace + gap insertion for laser cutting"
    )
    parser.add_argument('--input', '-i', required=True,
                       help='Input PNG file (black lines on white)')
    parser.add_argument('--output', '-o', required=True,
                       help='Output SVG file with gaps')
    parser.add_argument('--gap-length', type=float, default=3.0,
                       help='Length of each gap in pixels (default: 3)')
    parser.add_argument('--gap-spacing', type=float, default=40.0,
                       help='Distance between gap starts in pixels (default: 40)')
    parser.add_argument('--stroke-width', type=float, default=1.0,
                       help='Stroke width in output SVG (default: 1.0)')

    args = parser.parse_args()

    # Check dependencies
    if not check_potrace():
        return 1

    # Create temporary SVG for potrace output
    with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as tmp:
        tmp_svg = tmp.name

    try:
        # Step 1: Vectorize with potrace
        vectorize_with_potrace(args.input, tmp_svg)

        # Step 2: Parse the SVG paths
        paths, svg_attrs = parse_svg_paths(tmp_svg)

        if not paths:
            print("Error: No paths found in vectorized SVG")
            return 1

        # Step 3: Insert gaps in each path
        print(f"Inserting gaps (length={args.gap_length}px, spacing={args.gap_spacing}px)...")
        gapped_paths = []

        for i, path in enumerate(paths):
            path_length = path.length()

            if (i + 1) % 10 == 0 or path_length > 0:
                print(f"  Path {i+1}/{len(paths)}: length={path_length:.1f}px", end="")

            segments = insert_gaps_in_path(path, args.gap_length, args.gap_spacing)

            if (i + 1) % 10 == 0 or path_length > 0:
                print(f" -> {len(segments)} segments")

            gapped_paths.extend(segments)

        print(f"✓ Generated {len(gapped_paths)} path segments with gaps")

        # Step 4: Write output SVG
        write_svg_with_gaps(gapped_paths, svg_attrs, args.output, args.stroke_width)

        print(f"\n✓ Complete! Output written to {args.output}")

    finally:
        # Clean up temp file
        if os.path.exists(tmp_svg):
            os.unlink(tmp_svg)

    return 0


if __name__ == '__main__':
    exit(main())
