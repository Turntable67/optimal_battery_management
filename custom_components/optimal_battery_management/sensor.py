import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

DOMAIN = "optimal_battery_management"


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup sensor platform."""
    if discovery_info is None:
        _LOGGER.error("No discovery info provided. Check your configuration.yaml")
        return

    tariff_sensor = discovery_info.get("tariff_sensor")
    soc_sensor = discovery_info.get("soc_sensor")
    if not tariff_sensor or not soc_sensor:
        _LOGGER.error(
            "Tariff sensor or SoC sensor is not configured. Please check your configuration.yaml"
        )
        return

    optimal_schedule_sensor = OptimalBatteryManagementSensor(hass, discovery_info)
    optimal_charge_mode_sensor = OptimalChargeModeSensor(hass, f"sensor.{DOMAIN}")

    # Voeg beide sensoren toe
    async_add_entities([optimal_schedule_sensor, optimal_charge_mode_sensor])


class OptimalBatteryManagementSensor(SensorEntity):
    def __init__(self, hass, config):
        """Initialize the sensor."""
        self.hass = hass
        self._state = None
        self._attributes = {}
        self._tariff_sensor = config.get("tariff_sensor")
        self._soc_sensor = config.get("soc_sensor")
        self._depreciation_per_kwh = config.get("depreciation_per_kwh", 0.065)  # €/kWh
        self._min_profit = config.get("min_profit", 0.05)  # €/kWh
        self._max_capacity = config.get("max_capacity", 5.12)  # Default to 5.12 kWh if not specified
        self._charge_rate = config.get("charge_rate", 0.8)  # Load from config.yaml
        self._discharge_rate = config.get("discharge_rate", 0.8)  # Load from config.yaml
        self._last_trigger = "Interval [300s]"  # Default trigger is the periodic update
        self._last_update = None  # Timestamp of the last periodic update

        # Controleer of sensoren zijn ingesteld
        if not self._tariff_sensor or not self._soc_sensor:
            _LOGGER.error(
                "Tariff sensor or SoC sensor is not configured. Please check your configuration.yaml"
            )
            raise ValueError("Missing tariff_sensor or soc_sensor in configuration")

        # Volg wijzigingen in de tariff_sensor
        async_track_state_change_event(
            hass, self._tariff_sensor, self._handle_tariff_change_event
        )

        # Volg wijzigingen in de soc_sensor
        async_track_state_change_event(
            hass, self._soc_sensor, self._handle_soc_change_event
        )

    @property
    def name(self):
        return "Optimal Battery Management"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def should_poll(self):
        """Enable periodic polling."""
        return True

    @property
    def scan_interval(self):
        """Set custom scan interval to 300 seconds."""
        return timedelta(seconds=300)

    async def _handle_tariff_change_event(self, event):
        """Handle updates to the tariff sensor."""
        self._last_trigger = "tariff_sensor change"
        _LOGGER.info(
            "Tariff sensor '%s' state changed: %s",
            event.data.get("entity_id"),
            event.data.get("new_state"),
        )
        self._execute_update()

    async def _handle_soc_change_event(self, event):
        """Handle updates to the soc sensor."""
        self._last_trigger = "soc_sensor change"
        _LOGGER.info(
            "SoC sensor '%s' state changed: %s",
            event.data.get("entity_id"),
            event.data.get("new_state"),
        )
        self._execute_update()

    def _execute_update(self):
        """Force an update, bypassing the periodic interval restriction."""
        _LOGGER.debug(
            f"Executing immediate update for sensor 'Optimal Battery Management', "
            f"triggered by {self._last_trigger}"
        )
        self.schedule_update_ha_state(force_refresh=True)

    def update(self):
        """Update the sensor."""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))

        # Controleer of er 300 seconden zijn verstreken sinds de laatste periodieke update
        if self._last_trigger == "Interval [300s]" and self._last_update and (
            now - self._last_update < timedelta(seconds=300)
        ):
            _LOGGER.debug(
                f"Skipping periodic update for sensor 'Optimal Battery Management': "
                f"last update was less than 300 seconds ago."
            )
            return

        _LOGGER.debug(
            f"Updating sensor 'Optimal Battery Management', triggered by {self._last_trigger}"
        )

        # Timestamp van de laatste periodieke update bijwerken
        if self._last_trigger == "Interval [300s]":
            self._last_update = now

        # Reset last trigger to periodic interval after update
        self._last_trigger = "Interval [300s]"

        # Configurable parameters
        max_capacity = self._max_capacity
        charge_rate = self._charge_rate
        discharge_rate = self._discharge_rate

        # Get current battery state of charge
        soc = self.hass.states.get(self._soc_sensor)
        if not soc or soc.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"SoC sensor '{self._soc_sensor}' is unavailable or unknown. Skipping update.")
            return

        current_soc = float(soc.state) / 100.0  # Convert percentage to fraction
        current_capacity = max_capacity * current_soc

        # Calculate capacity needed to full charge and estimated time
        capacity_needed = max_capacity - current_capacity
        estimated_time = capacity_needed / charge_rate if charge_rate > 0 else float("inf")

        _LOGGER.debug(
            "Current SoC: %.2f%%, Current capacity: %.2f kWh, Max capacity: %.2f kWh, "
            "Capacity needed to full charge: %.2f kWh, Estimated time to full charge: %.2f hours",
            current_soc * 100,
            current_capacity,
            max_capacity,
            capacity_needed,
            estimated_time,
        )

        # Get forecast data
        tariff_sensor = self.hass.states.get(self._tariff_sensor)
        if not tariff_sensor or tariff_sensor.state == "unknown":
            _LOGGER.warning("Electricity tariff forecast sensor unavailable or unknown.")
            return

        forecast = tariff_sensor.attributes.get("forecast", [])
        if not forecast:
            _LOGGER.warning("No forecast data available.")
            return

        # Gebruik de Home Assistant tijdzone die al beschikbaar is
        local_tz = ZoneInfo(self.hass.config.time_zone)

        # Forecast direct omzetten naar lokale tijdzone
        for item in forecast:
            if isinstance(item["datetime"], str):  # Controleer of het een string is
                item["datetime"] = datetime.fromisoformat(item["datetime"][:-1]).replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
            elif isinstance(item["datetime"], datetime):  # Als het al een datetime is, zet het direct om
                item["datetime"] = item["datetime"].astimezone(local_tz)

        _LOGGER.debug("Converted forecast data to local timezone:")
        for item in forecast:
            _LOGGER.debug("Local Time: %s, Price: %.7f €/kWh", item["datetime"], item["electricity_price"] / 1e7)

        # Calculate the optimal schedule
        optimal_schedule = calculate_optimal_schedule(
            forecast, current_capacity, max_capacity, charge_rate, discharge_rate,
            self._depreciation_per_kwh, self._min_profit, self.hass.config.time_zone
        )


        # Log calculated charge and discharge schedules
        for period in optimal_schedule:
            action = period["action"]
            time = period["time"]
            price = period.get("price", 0)
            rate = period.get("rate", 0)
            if action == "charge":
                _LOGGER.info(
                    f"Charge period: {time} - {time + timedelta(hours=1)}, Price: {price:.7f} €/kWh, Rate: {rate:.2f} kW"
                )
            elif action == "discharge":
                _LOGGER.info(
                    f"Discharge period: {time}, Price: {price:.7f} €/kWh"
                )

        # Update the sensor state and attributes
        self._state = len(optimal_schedule)
        self._attributes = {"schedule": optimal_schedule}


class OptimalChargeModeSensor(SensorEntity):
    def __init__(self, hass, schedule_sensor):
        """Initialize the charge mode sensor."""
        self.hass = hass
        self._schedule_sensor = schedule_sensor
        self._state = "none"

    @property
    def name(self):
        return "Optimal Charge Mode"

    @property
    def state(self):
        return self._state

    @property
    def should_poll(self):
        """Enable periodic polling."""
        return True

    @property
    def scan_interval(self):
        """Set custom scan interval to 60 seconds."""
        return timedelta(seconds=60)

    def update(self):
        """Update the sensor state based on the schedule."""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))
        schedule = self.hass.states.get(self._schedule_sensor).attributes.get("schedule", [])
        _LOGGER.debug("Update the sensor state based on the schedule.")

        # Default state
        self._state = "none"

        # Log current time for debugging
        _LOGGER.debug(f"Home Assistant timezone: {self.hass.config.time_zone}")
        _LOGGER.debug(f"Current local time: {datetime.now(ZoneInfo(self.hass.config.time_zone))}")

        # Check current time against the schedule
        for item in schedule:
            start_time = item["time"]

            # Als start_time al een datetime is, gebruik het direct
            if isinstance(start_time, datetime):
                _LOGGER.debug(f"'time' is already a datetime object: {start_time}")
            else:
                # Probeer te converteren als het een string is
                try:
                    start_time = datetime.fromisoformat(start_time)
                except ValueError as e:
                    _LOGGER.error(f"Failed to parse schedule time: {item['time']}. Error: {e}")
                    continue

            # Controleer of we binnen het tijdsblok zitten
            end_time = start_time + timedelta(hours=1)
            _LOGGER.debug(
                f"Compare gevonden block voor {item["action"]} om {start_time} <= {now} < {end_time}"
            )
            if start_time <= now < end_time:
                self._state = item["action"]  # Either "charge" or "discharge"
                _LOGGER.debug(
                    f"Setting state of 'Optimal Charge Mode' to {self._state} based on schedule time: {start_time}"
                )
                break

        # Log de uiteindelijke state
        _LOGGER.debug(f"State of 'Optimal Charge Mode' is now: {self._state}")


def calculate_optimal_schedule(forecast, current_capacity, max_capacity, charge_rate, discharge_rate, depreciation_per_kwh, min_profit, time_zone):
    """Calculate optimal charge and discharge schedule based on forecast."""
    _LOGGER.debug("Starting calculation of optimal schedule.")

    now = datetime.now(ZoneInfo(time_zone))  # Gebruik de doorgegeven tijdzone

    # Log current time for debugging
    _LOGGER.debug(f"Home Assistant timezone: {time_zone}")
    _LOGGER.debug(f"Current local time: {datetime.now(ZoneInfo(time_zone))}")
    _LOGGER.debug(f"Current now time: {now}")
    
    # Calculate required charge capacity
    remaining_charge_capacity = max_capacity - current_capacity
    available_discharge_capacity = current_capacity

    # Filter future forecast data
    future_forecast = []
    for item in forecast:
        forecast_time = item["datetime"]
        if isinstance(forecast_time, str):
            forecast_time = datetime.fromisoformat(forecast_time).replace(tzinfo=ZoneInfo("UTC"))

        end_time = forecast_time + timedelta(hours=1)
        if now < end_time:
            future_forecast.append(item)

    if not future_forecast:
        _LOGGER.warning("No valid forecast data available for the future!")
        return []

    # Sort by cheapest and most expensive periods
    cheapest_periods = sorted(future_forecast, key=lambda x: x["electricity_price"])
    most_expensive_periods = sorted(future_forecast, key=lambda x: -x["electricity_price"])

    _LOGGER.debug("Cheapest periods: %s", cheapest_periods[:5])
    _LOGGER.debug("Most expensive periods: %s", most_expensive_periods[:5])

    # Calculate charge schedule
    charge_schedule = []
    total_charge_capacity = 0

    for item in cheapest_periods:
#        time = datetime.fromisoformat(item["datetime"])
        if isinstance(item["datetime"], str):
            time = datetime.fromisoformat(item["datetime"])
        else:
            time = item["datetime"]
        price = item["electricity_price"] / 1e7
        cost_to_charge = price + depreciation_per_kwh

        # Find the highest price in the most expensive periods
        max_price = most_expensive_periods[0]["electricity_price"] / 1e7 if most_expensive_periods else 0

        if cost_to_charge + min_profit < max_price:
            total_charge_capacity += charge_rate
            charge_schedule.append({"time": time, "price": price, "action": "charge", "rate": charge_rate})
            if total_charge_capacity >= remaining_charge_capacity:
                break
        else:
            _LOGGER.debug(
                "Skipping charge period at %s: Price + depreciation + min_profit (%.2f €/kWh) exceeds highest price (%.2f €/kWh).",
                time, cost_to_charge + min_profit, max_price
            )

    # Calculate discharge schedule
    discharge_schedule = []
    total_discharge_capacity = 0

    for item in most_expensive_periods:
#        time = datetime.fromisoformat(item["datetime"])
        if isinstance(item["datetime"], str):
            time = datetime.fromisoformat(item["datetime"])
        else:
            time = item["datetime"]

        price = item["electricity_price"] / 1e7

        # Skip overlapping times
        if any(c["time"] == time for c in charge_schedule):
            continue

        # Add to discharge period
        total_discharge_capacity += discharge_rate
        discharge_schedule.append({"time": time, "price": price, "action": "discharge"})

        if total_discharge_capacity >= available_discharge_capacity:
            break

    _LOGGER.debug("Calculated charge schedule: %s", charge_schedule)
    _LOGGER.debug("Calculated discharge schedule: %s", discharge_schedule)

    # Combine schedules
    full_schedule = charge_schedule + discharge_schedule
    full_schedule = sorted(full_schedule, key=lambda x: x["time"])
    _LOGGER.debug("Final optimal schedule: %s", full_schedule)

    return full_schedule
class Accu1ChargeModeSensor(SensorEntity):
    def __init__(self, hass):
        """Initialize the charge mode sensor for accu1."""
        self.hass = hass
        self._state = "none"

    @property
    def name(self):
        return "Accu1 Charge Mode"

    @property
    def state(self):
        return self._state

    @property
    def should_poll(self):
        """Enable periodic polling."""
        return True

    @property
    def scan_interval(self):
        """Set custom scan interval to 60 seconds."""
        return timedelta(seconds=60)
