from homeassistant.helpers.discovery import async_load_platform
import logging

_LOGGER = logging.getLogger(__name__)
DOMAIN = "optimal_battery_management"

async def async_setup(hass, config):
    """Set up the Optimal Battery Management component."""
    _LOGGER.debug("Setting up the Optimal Battery Management component.")

    # Controleer of de configuratie correct is geladen
    if DOMAIN not in config:
        _LOGGER.error("No configuration for %s found in configuration.yaml!", DOMAIN)
        return False

    hass.data[DOMAIN] = config[DOMAIN]
    _LOGGER.debug("Loaded configuration: %s", config[DOMAIN])

    # Laad de sensor en geef de configuratie door
    await async_load_platform(hass, "sensor", DOMAIN, config[DOMAIN], config)
    return True
