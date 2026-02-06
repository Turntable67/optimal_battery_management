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
    power_sensor = discovery_info.get("power_sensor")
    max_capacity = discovery_info.get("max_capacity", 5.12)  # Ophalen uit configuratie
    if not tariff_sensor or not soc_sensor or not power_sensor:
        _LOGGER.error(
            "Tariff sensor or SoC sensor is not configured. Please check your configuration.yaml"
        )
        return

    optimal_schedule_sensor = OptimalBatteryManagementSensor(hass, discovery_info)
    optimal_charge_mode_sensor = OptimalChargeModeSensor(hass, f"sensor.{DOMAIN}")
    optimal_avg_charge_price_sensor = AvgChargePriceSensor(hass, power_sensor, tariff_sensor, soc_sensor, max_capacity)
    optimal_avg_discharge_price_sensor = AvgDisChargePriceSensor(hass, power_sensor, tariff_sensor, soc_sensor, max_capacity)
    optimal_charging_efficiency_sensor = ChargingEfficiencySensor(hass, power_sensor, soc_sensor, max_capacity)
    optimal_discharging_efficiency_sensor = DisChargingEfficiencySensor(hass, power_sensor, soc_sensor, max_capacity)

    # Voeg de sensoren toe
    async_add_entities([
        optimal_schedule_sensor,
        optimal_charge_mode_sensor,
        optimal_avg_charge_price_sensor,
        optimal_avg_discharge_price_sensor,
        optimal_charging_efficiency_sensor,
        optimal_discharging_efficiency_sensor])
        
    hass.data["avg_charge_price"] = 0.0  # Initialiseer de variabele

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

        @property
        def unique_id(self):
            """Return a unique ID for this entity."""
            return f"{DOMAIN}_optimal_battery_management"

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
            "Tariff sensor '%s' state changed",
            event.data.get("entity_id"),
        )
        _LOGGER.debug(
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
        try:
            current_soc = float(soc.state) / 100.0
        except ValueError:
            _LOGGER.error(f"Invalid SoC value: {soc.state}")
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

        # Calculate the optimal schedule (roep function aan en kom terug om daarna het totale laad en ontlaad schema te tonen)
        optimal_schedule = calculate_optimal_schedule(
            self.hass,  # Voeg hass toe als eerste parameter
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
                    f"Dicharge period: {time} - {time + timedelta(hours=1)}, Price: {price:.7f} €/kWh, Rate: {rate:.2f} kW"
                )

        # Update the sensor state and attributes
        self._state = len(optimal_schedule)
        self._attributes = {"schedule": optimal_schedule}
        self.schedule_update_ha_state()


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
        """Werk de sensor bij met de laatste berekende waarde."""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))

        state = self.hass.states.get(self._schedule_sensor)
        if not state or "schedule" not in state.attributes:
            _LOGGER.warning(f"Schedule sensor '{self._schedule_sensor}' is unavailable. Skipping update.")
            return
        schedule = state.attributes.get("schedule", [])

#        schedule = self.hass.states.get(self._schedule_sensor).attributes.get("schedule", [])
        _LOGGER.debug("Update the sensor state based on the schedule.")

        self._state = "none"  # Standaard state

        for item in schedule:
            start_time = item["time"]

            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time)
                except ValueError as e:
                    _LOGGER.error(f"Failed to parse schedule time: {item['time']}. Error: {e}")
                    continue
            end_time = start_time + timedelta(hours=1)            
            _LOGGER.debug(f"Blok gevonden block ter controle {item['action']} om {start_time} <= {now} < {end_time}")

            if start_time <= now < end_time:
                current_price = item["price"]

                if item["action"] == "charge":
                    self._state = "charge"
                elif item["action"] == "discharge":
                    self._state = "discharge"

                break  # Stop bij de eerste match

        _LOGGER.debug(f"State of 'Optimal Charge Mode' is now: {self._state}")

        # **BELANGRIJK**: Forceer een update in Home Assistant
        self.schedule_update_ha_state()


class AvgChargePriceSensor(SensorEntity):
    """Sensor om de gemiddelde laadprijs te berekenen en bij te houden."""
    
    def __init__(self, hass, power_sensor, tariff_sensor, soc_sensor, max_capacity):
        """Initialiseer de sensor."""
        self.hass = hass
        self._power_sensor = power_sensor
        self._tariff_sensor = tariff_sensor
        self._soc_sensor = soc_sensor
        self._max_capacity = max_capacity
        self._state = 0.0  # Standaardwaarde
        
        # Startwaarden
        #self.calculated_energy = soc_percentage * self._max_capacity
        self.calculated_energy = 5.12  # kWh
        self.total_cost_energy = 1.00  # EUR
        self._last_update = None  # Tijdstempel van laatste update
        self._previous_power = 0  # Houd vorige vermogen bij om transities te detecteren

    @property
    def name(self):
        return "Average Charge Price"

    @property
    def state(self):
        return round(float(self._state), 4) if isinstance(self._state, (int, float)) else self._state

    @property
    def unit_of_measurement(self):
        return "€/kWh"

    @property
    def should_poll(self):
        """Periodieke updates inschakelen."""
        return True

    @property
    def scan_interval(self):
        """Bepaal hoe vaak de sensor zichzelf update (elke minuut)."""
        return timedelta(seconds=60)

    def update(self):
        """Werk de sensor bij met de laatste energie- en kostenberekening."""
        now = datetime.now()
        
        # Voorkom updates binnen 58 seconden
        if self._last_update and (now - self._last_update).total_seconds() < 58:
            _LOGGER.debug(f"Skipping update: Last update {(now - self._last_update).total_seconds()} was less than 58 seconds ago.")
            return
        
        self._last_update = now  # Update de laatste update tijd
        
        power_state = self.hass.states.get(self._power_sensor)
        tariff_state = self.hass.states.get(self._tariff_sensor)
        soc_state = self.hass.states.get(self._soc_sensor)
        
        if not power_state or power_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Power sensor '{self._power_sensor}' is unavailable. Skipping update.")
            return
        
        if not tariff_state or tariff_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Tariff sensor '{self._tariff_sensor}' is unavailable. Skipping update.")
            return
        
        if not soc_state or soc_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"SoC sensor '{self._soc_sensor}' is unavailable. Skipping update.")
            return
        
        try:
            power_value = float(power_state.state)  # Vermogen in Watt
            tariff_value = float(tariff_state.state)  # Tarief in €/kWh
            soc_percentage = float(soc_state.state) / 100.0  # SoC in fractie
        except ValueError as e:
            _LOGGER.error(f"Failed to convert sensor values: {e}")
            return
        
        _LOGGER.debug(f"Power Sensor: {power_value} W, Tariff: {tariff_value} €/kWh, SoC: {soc_percentage:.2f}")
        
        if self._previous_power <= 0 and power_value > 0:
            self.total_cost_energy = self.total_cost_energy * ((soc_percentage * self._max_capacity) / (self.calculated_energy + 0.00001))
            self.calculated_energy = soc_percentage * self._max_capacity
            _LOGGER.debug(f"Updated calculated_energy: {self.calculated_energy:.4f} kWh based on SoC.")
            _LOGGER.debug(f"Updated total_cost_energy: {self.total_cost_energy:.4f} EUR to keep avg cost consistent.")
        
        if power_value < 0:  # Alleen bij laden (negatieve waarde)
            charged_energy = (power_value * -1) / (60 * 1000)  # kWh per minuut
            cost_for_energy = tariff_value * charged_energy  # Kosten voor geladen energie
            
            self.calculated_energy += charged_energy
            self.total_cost_energy += cost_for_energy

            _LOGGER.debug(f"Charged Energy: {charged_energy:.6f} kWh, Cost: {cost_for_energy:.6f} EUR")
            _LOGGER.debug(f"Current Calculated Energy: {self.calculated_energy:.6f} kWh")
            _LOGGER.debug(f"Current Total Cost Energy: {self.total_cost_energy:.6f} EUR")

        
        if self.calculated_energy > 0:
            self._state = self.total_cost_energy / self.calculated_energy
        else:
            self._state = 0.0
        
        _LOGGER.debug(f"Updated Average Charge Price: {self._state:.6f} €/kWh")
        
        self._previous_power = power_value
        self.schedule_update_ha_state()

#-----
class AvgDisChargePriceSensor(SensorEntity):
    """Sensor om de gemiddelde ontlaadprijs te berekenen en bij te houden."""
    
    def __init__(self, hass, power_sensor, tariff_sensor, soc_sensor, max_capacity):
        """Initialiseer de sensor."""
        self.hass = hass
        self._power_sensor = power_sensor
        self._tariff_sensor = tariff_sensor
        self._soc_sensor = soc_sensor
        self._max_capacity = max_capacity
        self._state = 0.0  # Standaardwaarde
        
        # Startwaarden
        #self.calculated_energy = soc_percentage * self._max_capacity
        self.calculated_energy = 5.12  # kWh
        self.total_revenue_energy = 1.25  # EUR
        self._last_update = None  # Tijdstempel van laatste update
        self._previous_power = 0  # Houd vorige vermogen bij om transities te detecteren

    @property
    def name(self):
        return "Average DisCharge Price"

    @property
    def state(self):
        return round(float(self._state), 4) if isinstance(self._state, (int, float)) else self._state

    @property
    def unit_of_measurement(self):
        return "€/kWh"

    @property
    def should_poll(self):
        """Periodieke updates inschakelen."""
        return True

    @property
    def scan_interval(self):
        """Bepaal hoe vaak de sensor zichzelf update (elke minuut)."""
        return timedelta(seconds=60)

    def update(self):
        """Werk de sensor bij met de laatste energie- en kostenberekening."""
        now = datetime.now()
        
        # Voorkom updates binnen 58 seconden
        if self._last_update and (now - self._last_update).total_seconds() < 58:
            _LOGGER.debug(f"Skipping (d)update: Last update {(now - self._last_update).total_seconds()} was less than 58 seconds ago.")
            return
        
        self._last_update = now  # Update de laatste update tijd
        
        power_state = self.hass.states.get(self._power_sensor)
        tariff_state = self.hass.states.get(self._tariff_sensor)
        soc_state = self.hass.states.get(self._soc_sensor)
        
        if not power_state or power_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Power (d)sensor '{self._power_sensor}' is unavailable. Skipping update.")
            return
        
        if not tariff_state or tariff_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Tariff (d)sensor '{self._tariff_sensor}' is unavailable. Skipping update.")
            return
        
        if not soc_state or soc_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"SoC (d)sensor '{self._soc_sensor}' is unavailable. Skipping update.")
            return
        
        try:
            power_value = float(power_state.state)  # Vermogen in Watt
            tariff_value = float(tariff_state.state)  # Tarief in €/kWh
            soc_percentage = float(soc_state.state) / 100.0  # SoC in fractie
        except ValueError as e:
            _LOGGER.error(f"Failed to convert (d)sensor values: {e}")
            return
        
        _LOGGER.debug(f"Power (d)Sensor: {power_value} W, Tariff: {tariff_value} €/kWh, SoC: {soc_percentage:.2f}")
        
        if self._previous_power >= 0 and power_value < 0:
            self.total_revenue_energy = self.total_revenue_energy * ((soc_percentage * self._max_capacity) / (self.calculated_energy + 0.00001))
            self.calculated_energy = soc_percentage * self._max_capacity
            _LOGGER.debug(f"Updated calculated_energy: {self.calculated_energy:.4f} kWh based on SoC.")
            _LOGGER.debug(f"Updated total_revenue_energy: {self.total_revenue_energy:.4f} EUR to keep avg revenue consistent.")
        
        if power_value > 0:  # Alleen bij ontladen (positieve waarde)
            discharged_energy = (power_value * 1) / (60 * 1000)  # kWh per minuut
            revenue_for_energy = tariff_value * discharged_energy  # Kosten voor geladen energie
            
            self.calculated_energy += discharged_energy
            self.total_revenue_energy += revenue_for_energy

            _LOGGER.debug(f"DisCharged Energy: {discharged_energy:.6f} kWh, Cost: {revenue_for_energy:.6f} EUR")
            _LOGGER.debug(f"Current Calculated Energy: {self.calculated_energy:.6f} kWh")
            _LOGGER.debug(f"Current Total Revenue Energy: {self.total_revenue_energy:.6f} EUR")

        
        if self.calculated_energy > 0:
            self._state = self.total_revenue_energy / self.calculated_energy
        else:
            self._state = 0.0
        
        _LOGGER.debug(f"Updated Average DisCharge Price: {self._state:.6f} €/kWh")
        
        self._previous_power = power_value
        self.schedule_update_ha_state()

#-----


class ChargingEfficiencySensor(SensorEntity):
    """Sensor om de efficiëntie van het laden te berekenen."""

    def __init__(self, hass, power_sensor, soc_sensor, max_capacity):
        """Initialiseer de sensor."""
        self.hass = hass
        self._power_sensor = power_sensor
        self._soc_sensor = soc_sensor
        self._max_capacity = max_capacity
        self._state = None  # Initieel geen waarde
        self._start_soc = None  # SOC bij start van laadcyclus
        self._capaciteit_laden = 0.0  # Cumulatief geladen capaciteit
        self._last_power = None  # Laatste vermogen om laadstatus te detecteren
        self._last_soc = None
        self._last_update = None  # Tijdstempel van laatste update

    @property
    def name(self):
        return "Charging Efficiency"

    @property
    def state(self):
        return round(float(self._state), 2) if self._state is not None else None

    @property
    def unit_of_measurement(self):
        return "%"

    @property
    def should_poll(self):
        """Periodieke updates inschakelen."""
        return True

    @property
    def scan_interval(self):
        """Bepaal hoe vaak de sensor zichzelf update (elke minuut)."""
        return timedelta(seconds=60)

    def update(self):
        """Werk de sensor bij met de laatste laad- en efficiëntieberekening."""
        now = datetime.now()

        # Voorkom updates binnen 58 seconden
        if self._last_update and (now - self._last_update).total_seconds() < 58:
            #_LOGGER.debug("Skipping update: Last update was less than 60 seconds ago.")
            return

        self._last_update = now  # Update de laatste update tijd

        # Haal de sensorwaarden op
        power_state = self.hass.states.get(self._power_sensor)
        soc_state = self.hass.states.get(self._soc_sensor)

        if not power_state or power_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Power sensor '{self._power_sensor}' is unavailable. Skipping update.")
            return

        if not soc_state or soc_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"SoC sensor '{self._soc_sensor}' is unavailable. Skipping update.")
            return

        try:
            power_value = float(power_state.state)  # Vermogen in Watt
            current_soc = float(soc_state.state) / 100.0  # SoC omzetten naar fractie
        except ValueError as e:
            _LOGGER.error(f"Failed to convert sensor values: {e}")
            return

        # **Start nieuwe laadcyclus als het vermogen negatief wordt en er eerder geen laadcyclus actief was**
        if power_value < 0 and (self._last_power is None or self._last_power >= 0):
            self._start_soc = current_soc
            self._capaciteit_laden = 0.0
            _LOGGER.debug(f"Nieuwe laadcyclus gestart. Start SOC: {self._start_soc * 100:.2f}%")

        # **Accumuleren van de geladen energie per minuut**
        if power_value < 0:
            geladen_kwh = abs(power_value) / 1000 / 60  # kWh per minuut
            self._capaciteit_laden += geladen_kwh
            _LOGGER.debug(f"Charge Power: {power_value} W, SoC: {current_soc * 100:.2f}%")
            _LOGGER.debug(f"Laadcapaciteit verhoogd met {geladen_kwh:.6f} kWh. Totale laadcapaciteit: {self._capaciteit_laden:.6f} kWh.")

        # **Efficiëntieberekening bij SOC-wijziging**
        if self._start_soc is not None and current_soc > self._start_soc:
            delta_soc = current_soc - self._start_soc
            toegenomen_capaciteit = delta_soc * self._max_capacity  # kWh

            if current_soc > self._last_soc:

                if self._capaciteit_laden > 0 and current_soc > self._last_soc:
                    efficiency = min((toegenomen_capaciteit / self._capaciteit_laden) * 100, 100)
                    self._state = efficiency
                    _LOGGER.info(
                        f"Efficiëntie berekend: {efficiency:.2f}% "
                        f"(ΔSoC: {delta_soc * 100:.2f}%, Capaciteit: {toegenomen_capaciteit:.4f} kWh, "
                        f"Geaccumuleerde laadcapaciteit: {self._capaciteit_laden:.4f} kWh)."
                    )
                else:
                    _LOGGER.warning("Efficiëntie kon niet berekend worden. Mogelijk onvoldoende laadcapaciteit.")
            else:
                _LOGGER.debug("State of Charge is ongewijzigd (alleen berekening als toegenomen).")

        # **Opslaan van het laatste vermogen om overgang te detecteren**
        self._last_power = power_value
        self._last_soc = current_soc
        # **Update Home Assistant**
        self.schedule_update_ha_state()




class DisChargingEfficiencySensor(SensorEntity):
    """Sensor om de efficiëntie van het ontladen te berekenen."""

    def __init__(self, hass, power_sensor, soc_sensor, max_capacity):
        """Initialiseer de sensor."""
        self.hass = hass
        self._power_sensor = power_sensor
        self._soc_sensor = soc_sensor
        self._max_capacity = max_capacity
        self._state = None  # Initieel geen waarde
        self._start_soc = None  # SOC bij start van ontlaadcyclus
        self._capaciteit_ontladen = 0.0  # Cumulatief ontladen capaciteit
        self._last_power = None  # Laatste vermogen om ontlaadstatus te detecteren
        self._last_soc = None
        self._last_update = None  # Tijdstempel van laatste update

    @property
    def name(self):
        return "DisCharging Efficiency"

    @property
    def state(self):
        return round(float(self._state), 2) if self._state is not None else None

    @property
    def unit_of_measurement(self):
        return "%"

    @property
    def should_poll(self):
        """Periodieke updates inschakelen."""
        return True

    @property
    def scan_interval(self):
        """Bepaal hoe vaak de sensor zichzelf update (elke minuut)."""
        return timedelta(seconds=60)

    def update(self):
        """Werk de sensor bij met de laatste ontlaad- en efficiëntieberekening."""
        now = datetime.now()

        # Voorkom updates binnen 58 seconden
        if self._last_update and (now - self._last_update).total_seconds() < 59:
            return

        self._last_update = now  # Update de laatste update tijd

        # Haal de sensorwaarden op
        power_state = self.hass.states.get(self._power_sensor)
        soc_state = self.hass.states.get(self._soc_sensor)

        if not power_state or power_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"Power sensor '{self._power_sensor}' is unavailable. Skipping update.")
            return

        if not soc_state or soc_state.state in ["unknown", "unavailable"]:
            _LOGGER.warning(f"SoC sensor '{self._soc_sensor}' is unavailable. Skipping update.")
            return

        try:
            power_value = float(power_state.state)  # Vermogen in Watt
            current_soc = float(soc_state.state) / 100.0  # SoC omzetten naar fractie
        except ValueError as e:
            _LOGGER.error(f"Failed to convert sensor values: {e}")
            return

        # **Start nieuwe ontlaadcyclus als het vermogen positief wordt en er eerder geen ontlaadcyclus actief was**
        if power_value > 0 and (self._last_power is None or self._last_power <= 0):
            self._start_soc = current_soc
            self._capaciteit_ontladen = 0.0
            _LOGGER.debug(f"Nieuwe ontlaadcyclus gestart. Start SOC: {self._start_soc * 100:.2f}%")

        # **Accumuleren van de ontladen energie per minuut**
        if power_value > 0:
            ontladen_kwh = power_value / 1000 / 60  # kWh per minuut
            self._capaciteit_ontladen += ontladen_kwh
            _LOGGER.debug(f"Ontlaadcapaciteit verhoogd met {ontladen_kwh:.6f} kWh. Totale ontlaadcapaciteit: {self._capaciteit_ontladen:.6f} kWh.")
            

        # **Efficiëntieberekening bij SOC-wijziging**
        if self._start_soc is not None and current_soc < self._start_soc:
            delta_soc = self._start_soc - current_soc
            afgenomen_capaciteit = delta_soc * self._max_capacity  # kWh

            if current_soc < self._last_soc:  # Alleen berekenen als SoC écht is gedaald

                if self._capaciteit_ontladen > 0:
                    efficiency = min((self._capaciteit_ontladen / afgenomen_capaciteit) * 100, 100)
                    self._state = efficiency
                    _LOGGER.info(
                        f"Efficiëntie berekend: {efficiency:.2f}% "
                        f"(ΔSoC: {delta_soc * 100:.2f}%, Capaciteit: {afgenomen_capaciteit:.4f} kWh, "
                        f"Geaccumuleerde ontlaadcapaciteit: {self._capaciteit_ontladen:.4f} kWh)."
                    )
                else:
                    _LOGGER.warning("Efficiëntie kon niet berekend worden. Mogelijk onvoldoende ontlaadcapaciteit.")
            else:
                _LOGGER.debug("State of Charge is ongewijzigd (alleen berekening als afgenomen).")

        self._last_power = power_value
        self._last_soc = current_soc
        self.schedule_update_ha_state()

def calculate_optimal_schedule(hass, forecast, current_capacity, max_capacity, charge_rate, discharge_rate, depreciation_per_kwh, min_profit, time_zone):
    """Calculate optimal charge and discharge schedule based on forecast."""
    _LOGGER.info("Starting calculation of optimal schedule.")

    now = datetime.now(ZoneInfo(time_zone))  # Gebruik de doorgegeven tijdzone

    # Log current time for debugging
    _LOGGER.info(f"Home Assistant timezone: {time_zone}")
    #_LOGGER.debug(f"Current local time: {datetime.now(ZoneInfo(time_zone))}")
    _LOGGER.info(f"Current now time: {now}")
    
    # Calculate required charge capacity
    remaining_charge_capacity = max_capacity - current_capacity
    available_discharge_capacity = current_capacity

    # Filter future forecast data
    future_forecast = []
    hours_ahead = now + timedelta(hours=11)  # Define the cutoff time
    
    for item in forecast:
        forecast_time = item["datetime"]
        if isinstance(forecast_time, str):
            forecast_time = datetime.fromisoformat(forecast_time).replace(tzinfo=ZoneInfo("UTC"))

        block_time = forecast_time + timedelta(hours=1)

        if now < block_time <= hours_ahead:     # niet te ver vooruit anders nu als tijden voor morgen (4 tijden eerste 10 uur
            future_forecast.append(item)
            _LOGGER.debug("Forecast_time: %s till block_time %s added", forecast_time, block_time )
        else:
            _LOGGER.debug("NO Forecast_time for: %s till block_time %s", forecast_time, block_time)
            if block_time > hours_ahead:
                break  # Alle volgende blokken liggen buiten de 10-uursgrens, dus stoppen

    if not future_forecast:
        _LOGGER.warning("No valid forecast data available for the future!")
        return []

    # Sort by cheapest and most expensive periods
    cheapest_periods = sorted(future_forecast, key=lambda x: x["electricity_price"])[:3]
    most_expensive_periods = sorted(future_forecast, key=lambda x: -x["electricity_price"])[:3]
    most_expensive_period = sorted(future_forecast, key=lambda x: -x["electricity_price"])[:1]
    average_peak_price = sum(item["electricity_price"] / 1e7 for item in most_expensive_periods) / len(most_expensive_periods)

    _LOGGER.debug("Cheapest periods: %s", cheapest_periods)
    _LOGGER.debug("Most expensive periods: %s", most_expensive_periods)
    _LOGGER.debug("Most expensive period: %s", most_expensive_period)
    _LOGGER.debug("AVG expensive periods: %.3f €/kWh", average_peak_price)

    # Calculate charge schedule
    charge_schedule = []
    
    #hier zou je later de actuele waarde kunnen vullen soc*totaal
    total_charge_capacity = 0
    
    seen_charge_times = set()  # bewaakt unieke (tijd, "charge") entries

    # Charge schedule zonder beperkingen
    for item in cheapest_periods:
        if isinstance(item["datetime"], str):
            time = datetime.fromisoformat(item["datetime"])
        else:
            time = item["datetime"]

        price = item["electricity_price"] / 1e7

        key = (time, "charge")
        if key in seen_charge_times:
            continue
        seen_charge_times.add(key)

        charge_schedule.append({
            "time": time,
            "price": price,
            "action": "charge",
            "rate": charge_rate
        })

    
        _LOGGER.debug(
            "Adding charge period at %s: Price %.2f €/kWh.",
            time, price
        )


    # Filter forecastdata van nu tot aan de duurste piekperiode
    pre_peak_forecast = []

    # Haal de tijd van het duurste blok op
    most_expensive_time = most_expensive_period[0]["datetime"]
    if isinstance(most_expensive_time, str):
        most_expensive_time = datetime.fromisoformat(most_expensive_time).replace(tzinfo=ZoneInfo("UTC"))

    for item in forecast:
        forecast_time = item["datetime"]
        if isinstance(forecast_time, str):
            forecast_time = datetime.fromisoformat(forecast_time).replace(tzinfo=ZoneInfo("UTC"))

        block_time = forecast_time + timedelta(hours=1)

        # Alleen blokken opnemen die eindigen vóór de piek
        if now < block_time <= most_expensive_time:
            pre_peak_forecast.append(item)
            _LOGGER.debug("PRE-PEAK Forecast_time: %s till block_time %s added", forecast_time, block_time)
        else:
            _LOGGER.debug("NO PRE-PEAK Forecast_time for: %s till block_time %s", forecast_time, block_time)
            if block_time > most_expensive_time:
                break  # Alle volgende blokken liggen ook na de piek, dus stoppen

    if not pre_peak_forecast:
        _LOGGER.warning("No valid pre-peak forecast data available!")
    else:
        _LOGGER.debug("pre_peak_forecast: %s", pre_peak_forecast)
        cheapest_pre_peak_periods = sorted(pre_peak_forecast, key=lambda x: x["electricity_price"])[:3]
        _LOGGER.debug("Pre_peak_periods: %s", cheapest_pre_peak_periods)

        # Extra pre-peak charge momenten (optioneel toevoegen als ze voldoen aan de prijsvoorwaarde)

        for item in cheapest_pre_peak_periods:
            if isinstance(item["datetime"], str):
                time = datetime.fromisoformat(item["datetime"])
            else:
                time = item["datetime"]

            price = item["electricity_price"] / 1e7  # Omzetten naar €/kWh

            # Voorwaarde: alleen toevoegen als prijs lager is dan piek - marge
            if price < (average_peak_price - (depreciation_per_kwh + min_profit)):
                key = (time, "charge")
                if key in seen_charge_times:
                    continue
                seen_charge_times.add(key)

                charge_schedule.append({
                    "time": time,
                    "price": price,
                    "action": "charge",
                    "rate": charge_rate
                })

                _LOGGER.debug(
                    "Adding PRE-PEAK charge period at %s: Price %.3f €/kWh (threshold: %.3f)",
                    time, price, average_peak_price - (depreciation_per_kwh + min_profit)
                )
            else:
                _LOGGER.debug(
                    "Skipping PRE-PEAK charge period at %s: Price %.3f €/kWh is above threshold %.3f",
                    time, price, average_peak_price - (depreciation_per_kwh + min_profit)
                )

    # Calculate discharge schedule
    discharge_schedule = []
    total_discharge_capacity = 0

    # Ophalen van de gemiddelde laadprijs uit Home Assistant
    avg_charge_price_sensor = hass.states.get("sensor.average_charge_price")
    if not avg_charge_price_sensor or avg_charge_price_sensor.state in ["unknown", "unavailable"]:
        avg_charge_price = 0  # Stel standaard op 0 als niet beschikbaar
    else:
        avg_charge_price = float(avg_charge_price_sensor.state)
        

    # Bepaal de drempelwaarde (kostprijs van laden + afschrijving + minimale winst)
    cost_threshold = avg_charge_price + depreciation_per_kwh + min_profit
    _LOGGER.info(
        "Calculated cost Threshold: %.3f €/kWh <= average charge (%.3f) + depreciation (%.3f) + min_profit (%.3f).",
        cost_threshold, avg_charge_price, depreciation_per_kwh, min_profit
    )

    # Discharge schedule met controle op afschrijving en minimale winst
    discharge_schedule = []
    for item in most_expensive_periods:
        if isinstance(item["datetime"], str):
            time = datetime.fromisoformat(item["datetime"])
        else:
            time = item["datetime"]

        price = item["electricity_price"] / 1e7  # Prijs omzetten naar €/kWh

        # Controle: Alleen ontladen als de prijs hoger is dan de kostprijs
        if price > cost_threshold:
            discharge_schedule.append({
                "time": time, 
                "price": price, 
                "action": "discharge", 
                "rate": discharge_rate
            })

            _LOGGER.debug(
                "Adding discharge period at %s: Price %.2f €/kWh (Threshold: %.2f €/kWh).",
                time, price, cost_threshold
            )
        else:
            _LOGGER.debug(
                "Skipping discharge period at %s: Price %.2f €/kWh is below threshold %.2f €/kWh.",
                time, price, cost_threshold
            )

    _LOGGER.debug("Calculated charge schedule: %s", charge_schedule)
    _LOGGER.debug("Calculated discharge schedule: %s", discharge_schedule)

    # Combine schedules
    full_schedule = charge_schedule + discharge_schedule
    full_schedule = sorted(full_schedule, key=lambda x: x["time"])
    _LOGGER.info("Final optimal schedule: %s", full_schedule)

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
