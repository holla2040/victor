# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Victor is a tool for vectorizing images for laser cutting. It converts photographs into precise black-and-white line drawings with strategically placed gaps, making them suitable for laser cutting operations.

The workflow is:
1. Generate line art from photos using AI prompts (two variations: with/without background)
2. Vectorize the raster line art using the `vectorize_fast.py` script
3. Output includes gap insertion for laser cutting optimization

## Dependencies

Required system packages:
- `potrace` - Core vectorization tool
  - Ubuntu/Debian: `sudo apt install potrace`
  - macOS: `brew install potrace`

Required Python packages:
- `pip install numpy opencv-python-headless svgpathtools`

## Running the Vectorization Tool

Basic command structure:
```bash
python vectorize_fast.py \
    --input <input_image.png> \
    --output <output.svg> \
    --gap-length <pixels> \
    --gap-spacing <pixels> \
    --stroke-width <width>
```

Example with typical parameters:
```bash
python vectorize_fast.py \
    --input image-without.png \
    --output image-without.svg \
    --gap-length 20 \
    --gap-spacing 400 \
    --stroke-width 1.0
```

Parameters:
- `--gap-length`: Length of each gap in pixels (default: 3)
- `--gap-spacing`: Distance between gap starts in pixels (default: 40)
- `--stroke-width`: Stroke width in output SVG (default: 1.0)

## Image Preparation Prompts

The README.md contains two AI prompts for generating line art:

**PROMPT A (with background)**: Creates line drawings including simplified background elements like walls, doors, windows, and major equipment.

**PROMPT B (without background)**: Creates line drawings of only the subjects with completely blank white backgrounds.

Both require:
- Single uniform line width
- Clean, smooth, continuous lines
- No shading, gradients, or textures
- Output resolution: 4096-7680 pixels
- Black lines on white background

## Architecture

The vectorization pipeline in `vectorize_fast.py`:

1. **Image Preprocessing** (`convert_to_pbm`): Converts PNG to binary BMP format that potrace can process
2. **Vectorization** (`vectorize_with_potrace`): Uses potrace with optimized parameters:
   - Corner threshold: 0.5 (sharper corners)
   - Speckle suppression: 2px
   - Curve optimization tolerance: 1.0
3. **Path Parsing** (`parse_svg_paths`): Extracts SVG path data using svgpathtools
4. **Gap Insertion** (`insert_gaps_in_path`): Linear-time algorithm that:
   - Places gaps at regular intervals along each path
   - Handles edge cases (short paths, path ends)
   - Returns list of path segments with gaps removed
5. **SVG Generation** (`write_svg_with_gaps`): Outputs final SVG with:
   - Y-axis flip correction (potrace outputs upside-down)
   - Configurable stroke properties
   - Clean, optimized path data

The gap insertion algorithm is designed for laser cutting efficiency - gaps allow the laser to turn off periodically, reducing heat buildup and improving cut quality.
