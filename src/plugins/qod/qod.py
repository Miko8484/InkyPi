from plugins.base_plugin.base_plugin import BasePlugin
import requests
import logging

logger = logging.getLogger(__name__)

ZENQUOTES_API_URL = "https://zenquotes.io/api/today"


class Qod(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        quote_data = self.get_quote()

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params = {
            "quote": quote_data.get("quote", ""),
            "author": quote_data.get("author", ""),
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "qod.html", "qod.css", template_params)
        return image

    def get_quote(self):
        try:
            response = requests.get(ZENQUOTES_API_URL, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                return {
                    "quote": data[0].get("q", ""),
                    "author": data[0].get("a", "")
                }
        except Exception as e:
            logger.error(f"Failed to fetch quote: {str(e)}")

        return {
            "quote": "The only way to do great work is to love what you do.",
            "author": "Steve Jobs"
        }
