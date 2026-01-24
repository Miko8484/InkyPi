from flask import Blueprint, request, jsonify, current_app, render_template, send_file
import os
from datetime import datetime
from PIL import Image
from io import BytesIO

main_bp = Blueprint("main", __name__)

# Spectra 6 e-ink display palette: black, white, red, yellow, blue, green
SPECTRA_6_PALETTE = [
    0, 0, 0,        # Black
    255, 255, 255,  # White
    255, 0, 0,      # Red
    255, 255, 0,    # Yellow
    0, 0, 255,      # Blue
    0, 255, 0,      # Green
]

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

@main_bp.route('/api/current_image')
def get_current_image():
    """Serve current_image as BMP optimized for Spectra 6 e-ink display."""
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

    # Convert image to Spectra 6 palette BMP
    img = Image.open(image_path).convert('RGB')

    # Resize to display dimensions (800x480) if larger
    DISPLAY_WIDTH, DISPLAY_HEIGHT = 800, 480
    if img.width > DISPLAY_WIDTH or img.height > DISPLAY_HEIGHT:
        img.thumbnail((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)

    # Create a palette image with Spectra 6 colors
    palette_img = Image.new('P', (1, 1))
    # Pad palette to 256 colors (768 values) as required by PIL
    padded_palette = SPECTRA_6_PALETTE + [0] * (768 - len(SPECTRA_6_PALETTE))
    palette_img.putpalette(padded_palette)

    # Quantize to the Spectra 6 palette
    quantized = img.quantize(colors=6, palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)

    # Save to BMP in memory
    bmp_buffer = BytesIO()
    quantized.save(bmp_buffer, format='BMP')
    bmp_buffer.seek(0)

    # Send the BMP file with Last-Modified header
    response = send_file(bmp_buffer, mimetype='image/bmp', download_name='current_image.bmp')
    response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
    response.headers['Cache-Control'] = 'no-cache'
    return response