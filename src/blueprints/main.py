from flask import Blueprint, request, jsonify, current_app, render_template, send_file, Response
import os
from datetime import datetime
from PIL import Image
import numpy as np

main_bp = Blueprint("main", __name__)

# Waveshare 7.3" Spectra6 display configuration
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# Spectra6 6-color palette as FLAT list for putpalette()
# Color indices: 0=Black, 1=White, 2=Yellow, 3=Red, 4=Blue, 5=Green
PALETTE_FLAT = [
    0, 0, 0,          # 0 = Black
    255, 255, 255,    # 1 = White
    0, 128, 0,        # 2 = Green
    0, 0, 255,        # 3 = Blue
    255, 0, 0,        # 4 = Red
    255, 255, 0,      # 5 = Yellow
]

def _create_palette_image():
    """Create palette image for quantization."""
    palette_img = Image.new('P', (1, 1))
    full_palette = PALETTE_FLAT + [128, 128, 128] * (256 - 6)
    palette_img.putpalette(full_palette)
    return palette_img

PALETTE_IMAGE = _create_palette_image()


def convert_to_display_format(image_path):
    """Convert image to 4bpp packed format."""
    img = Image.open(image_path).convert('RGB')
    img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)

    quantized = img.quantize(
        colors=6,
        palette=PALETTE_IMAGE,
        dither=Image.Dither.FLOYDSTEINBERG
    )

    pixels = np.array(quantized, dtype=np.uint8)
    flat = pixels.flatten()
    packed = (flat[0::2] << 4) | flat[1::2]

    return bytes(packed)


@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

@main_bp.route('/api/test_pattern')
def test_pattern():
    """Serve raw color test pattern."""
    pattern_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'test_pattern_8colors.raw')
    with open(pattern_path, 'rb') as f:
        data = f.read()
    return Response(data, mimetype='application/octet-stream')

@main_bp.route('/api/current_image')
def get_current_image():
    """Serve current image."""
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'current_image.png')

    if not os.path.exists(image_path):
        return jsonify({"error": "Image not found"}), 404

    file_mtime = int(os.path.getmtime(image_path))
    last_modified = datetime.fromtimestamp(file_mtime)

    if_modified_since = request.headers.get('If-Modified-Since')
    if if_modified_since:
        try:
            client_mtime = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S %Z')
            if file_mtime <= int(client_mtime.timestamp()):
                return '', 304
        except (ValueError, AttributeError):
            pass

    output_format = request.args.get('format', 'spectra6').lower()

    if output_format in ['raw', 'spectra6']:
        try:
            packed_data = convert_to_display_format(image_path)
            response = Response(packed_data, mimetype='application/octet-stream')
            response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['Content-Length'] = len(packed_data)
            return response
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        response = send_file(image_path, mimetype='image/png')
        response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response