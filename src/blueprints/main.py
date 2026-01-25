from flask import Blueprint, request, jsonify, current_app, render_template, send_file, Response
import os
from datetime import datetime
from PIL import Image
import numpy as np

main_bp = Blueprint("main", __name__)

# Waveshare 7.3" Spectra6 display configuration
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# RGB values for each color index
PALETTE_RGB = np.array([
    [0, 0, 0],        # 0 = Black
    [255, 255, 255],  # 1 = White
    [0, 128, 0],      # 2 = Green
    [0, 0, 255],      # 3 = Blue
    [255, 0, 0],      # 4 = Red
    [255, 255, 0],    # 5 = Yellow
], dtype=np.float32)


def find_nearest_color(pixel):
    """Find the nearest palette color index for a pixel."""
    distances = np.sum((PALETTE_RGB - pixel) ** 2, axis=1)
    return np.argmin(distances)


def convert_to_display_format(image_path):
    """Convert image to 4bpp packed format with proper 6-color quantization."""
    img = Image.open(image_path).convert('RGB')
    img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
    
    # Convert to float array for dithering
    pixels = np.array(img, dtype=np.float32)
    
    # Output indices array
    indices = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH), dtype=np.uint8)
    
    # Floyd-Steinberg dithering with guaranteed 6-color output
    for y in range(DISPLAY_HEIGHT):
        for x in range(DISPLAY_WIDTH):
            old_pixel = np.clip(pixels[y, x], 0, 255)
            
            # Find nearest color in our 6-color palette
            idx = find_nearest_color(old_pixel)
            indices[y, x] = idx
            
            new_pixel = PALETTE_RGB[idx]
            error = old_pixel - new_pixel
            
            # Distribute error (Floyd-Steinberg)
            if x + 1 < DISPLAY_WIDTH:
                pixels[y, x + 1] += error * 7 / 16
            if y + 1 < DISPLAY_HEIGHT:
                if x > 0:
                    pixels[y + 1, x - 1] += error * 3 / 16
                pixels[y + 1, x] += error * 5 / 16
                if x + 1 < DISPLAY_WIDTH:
                    pixels[y + 1, x + 1] += error * 1 / 16
    
    # Pack 2 pixels per byte
    flat = indices.flatten()
    packed = (flat[0::2] << 4) | flat[1::2]
    
    return bytes(packed)


def convert_to_display_format_fast(image_path):
    """Faster conversion using vectorized operations (less accurate dithering)."""
    img = Image.open(image_path).convert('RGB')
    img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
    
    pixels = np.array(img, dtype=np.float32)
    
    # Reshape for broadcasting: (H, W, 1, 3) vs (6, 3)
    pixels_expanded = pixels.reshape(DISPLAY_HEIGHT, DISPLAY_WIDTH, 1, 3)
    palette_expanded = PALETTE_RGB.reshape(1, 1, 6, 3)
    
    # Calculate distances to all palette colors
    distances = np.sum((pixels_expanded - palette_expanded) ** 2, axis=3)
    
    # Find nearest color index for each pixel
    indices = np.argmin(distances, axis=2).astype(np.uint8)
    
    # Pack 2 pixels per byte
    flat = indices.flatten()
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