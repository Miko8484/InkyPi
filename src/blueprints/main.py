from flask import Blueprint, request, jsonify, current_app, render_template, send_file, Response
import os
from datetime import datetime
from PIL import Image
import numpy as np

main_bp = Blueprint("main", __name__)

# Waveshare 7.3" Spectra6 display configuration
SPECTRA6_WIDTH = 800
SPECTRA6_HEIGHT = 480

# Spectra6 6-color palette as FLAT list for putpalette()
# Color indices: 0=Black, 1=White, 2=Yellow, 3=Red, 4=Blue, 5=Green
SPECTRA6_PALETTE_FLAT = [
    0, 0, 0,          # 0 = Black
    255, 255, 255,    # 1 = White
    255, 255, 0,      # 2 = Yellow
    255, 0, 0,        # 3 = Red
    0, 0, 255,        # 4 = Blue
    0, 128, 0,        # 5 = Green
]

# Pre-create palette image once at module load
def _create_palette_image():
    """Create a palette image for quantization."""
    palette_img = Image.new('P', (1, 1))
    # Pad palette to 256 colors (768 values = 256 * 3 RGB)
    full_palette = SPECTRA6_PALETTE_FLAT + [0] * (768 - len(SPECTRA6_PALETTE_FLAT))
    palette_img.putpalette(full_palette)
    return palette_img

PALETTE_IMAGE = _create_palette_image()


def convert_to_spectra6(image_path):
    """
    Convert an image to Spectra6 6-color format for ESP32.
    Returns packed binary data where each byte contains 2 pixels (4 bits each).
    """
    # Load and resize image
    img = Image.open(image_path).convert('RGB')
    img = img.resize((SPECTRA6_WIDTH, SPECTRA6_HEIGHT), Image.Resampling.LANCZOS)

    # Quantize to 6-color palette with Floyd-Steinberg dithering
    quantized = img.quantize(
        colors=6,
        palette=PALETTE_IMAGE,
        dither=Image.Dither.FLOYDSTEINBERG
    )

    # Get pixel data as numpy array
    pixels = np.array(quantized, dtype=np.uint8)

    # Pack 2 pixels per byte (high nibble = first pixel, low nibble = second pixel)
    flat = pixels.flatten()
    packed = (flat[0::2] << 4) | flat[1::2]

    return bytes(packed)


@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())


@main_bp.route('/api/current_image')
def get_current_image():
    """
    Serve current_image.png with conditional request support (If-Modified-Since).

    Query parameters:
        format: 'spectra6' (default) or 'png' for original image

    For format=spectra6:
        - Returns raw binary data (800x480 pixels, 2 pixels per byte)
        - Each byte: high nibble = first pixel, low nibble = second pixel
        - Color indices: 0=Black, 1=White, 2=Yellow, 3=Red, 4=Blue, 5=Green
        - Total size: 192,000 bytes
    """
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'current_image.png')

    if not os.path.exists(image_path):
        return jsonify({"error": "Image not found"}), 404

    # Get the file's last modified time (truncate to seconds to match HTTP header precision)
    file_mtime = int(os.path.getmtime(image_path))
    last_modified = datetime.fromtimestamp(file_mtime)

    # Check If-Modified-Since header
    if_modified_since = request.headers.get('If-Modified-Since')
    if if_modified_since:
        try:
            # Parse the If-Modified-Since header
            client_mtime = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S %Z')
            client_mtime_seconds = int(client_mtime.timestamp())

            # Compare (both now in seconds, no sub-second precision)
            if file_mtime <= client_mtime_seconds:
                return '', 304
        except (ValueError, AttributeError):
            pass

    # Check requested format
    output_format = request.args.get('format', 'spectra6').lower()

    if output_format == 'spectra6':
        # Convert to Spectra6 6-color format for ESP32
        try:
            packed_data = convert_to_spectra6(image_path)
            response = Response(packed_data, mimetype='application/octet-stream')
            response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['Content-Length'] = len(packed_data)
            response.headers['X-Image-Width'] = str(SPECTRA6_WIDTH)
            response.headers['X-Image-Height'] = str(SPECTRA6_HEIGHT)
            return response
        except Exception as e:
            return jsonify({"error": f"Failed to convert image: {str(e)}"}), 500
    else:
        # Send the file with Last-Modified header (original PNG format)
        response = send_file(image_path, mimetype='image/png')
        response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
        response.headers['Cache-Control'] = 'no-cache'
        return response