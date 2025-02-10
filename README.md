# Optimal Battery Management for Home Assistant

Unofficial integration to retrieve the day ahead prices from Zonneplan and use this data to calculate when to charge and dischage home battery.

## Available sensors
### optimal_battery_management
  - Number of periods found: 
  - Scheduled periodes for charging and discharging
    
### optimal_charge_mode:
  - state for battery

## Installation

### Install manually
<details>
   
1. Install this platform by creating a `custom_components` folder in the same folder as your configuration.yaml, if it doesn't already exist.
2. Create another folder `optimal_battery_management` in the `custom_components` folder. 
3. Copy all files from `custom_components/optimal_battery_management` into the newly created `optimal_battery_management` folder.
4. Restart HA
5. Add settings to your configuration.yaml

optimal_battery_management:
  tariff_sensor: sensor.zonneplan_current_electricity_tariff
  soc_sensor: sensor.accu1_battery_soc
  capacity: 5.12  # Accu capaciteit in kWh
  charge_rate: 1.0  # Laadsnelheid in kW
  discharge_rate: 2.0  # Ontlaadsnelheid in kW
  depreciation_per_kwh: 0.065  # €/kWh afschrijving o.b.v. 6000 cycles
  min_profit: 0.020
</details>


