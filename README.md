# Optimal Battery Management for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/fsaris/home-assistant-zonneplan-one?style=for-the-badge)
![Active installations](https://badge.t-haber.de/badge/zonneplan_one?kill_cache=1)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://hacs.xyz/)
![stability-stable](https://img.shields.io/badge/stability-stable-green.svg?style=for-the-badge&color=green)
![GitHub License](https://img.shields.io/github/license/fsaris/home-assistant-zonneplan-one?style=for-the-badge)

Unofficial integration to retrieve the day ahead prices from Zonneplan and use this data to calculate when to charge and dischage home battery.

## Available sensors
### optimal_battery_management
  - Number of periods found: 
  - Scheduled periodes for charging and discharging
    
### optimal_charge_mode:
<details>
<summary>Sensors available if you have a Zonneplan Connect P1 reader</summary>
   
   - Electricity consumption: `W`
   - Electricity production: `W`
   - Electricity average: `W` (average use over the last 5min)
   - Electricity first measured: `date` _(default disabled)_
   - Electricity last measured: `date`
   - Electricity last measured production: `date`
   - Gas first measured: `date` _(default disabled)_
   - Gas last measured: `date`
</details>

## Installation

### Install with HACS (recommended)

Ensure you have [HACS](https://hacs.xyz/) installed. 

[![Direct link to Zonneplan in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fsaris&repository=home-assistant-zonneplan-one)

1. Click the above My button or search HACS integrations for **Zonneplan**
1. Click `Install`
1. Restart Home Assistant
1. Continue with [setup](#setup)

### Install manually
<details>
   
1. Install this platform by creating a `custom_components` folder in the same folder as your configuration.yaml, if it doesn't already exist.
2. Create another folder `zonneplan_one` in the `custom_components` folder. 
3. Copy all files from `custom_components/zonneplan_one` into the newly created `zonneplan_one` folder.
</details>

### Installing main/beta version using HACS
<details>
   
1. Go to `HACS` => `Integrations`
1. Click on the three dots icon in right bottom of the **Zonneplan** card
1. Click `Reinstall`
1. Make sure `Show beta versions` is checked
1. Select version `main`
1. Click install and restart HA
</details>

## Setup
[![Open your Home Assistant instance and start setting up Zonneplan.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zonneplan_one)
1. Click the above My button _(or navigate to `Configuration` -> `Integrations` -> `+ Add integration` and search for and select `Zonneplan ONE`)_
1. Enter you `emailaddress` you also use in the **Zonneplan** app
1. You will get an email to verify the login.
1. Click "Save"
1. Enjoy

## Setup Energy Dashboard
[![Open your Home Assistant instance and start setting up Energy sensors.](https://my.home-assistant.io/badges/config_energy.svg)](https://my.home-assistant.io/redirect/config_energy/)

#### Solar production
`Zonneplan Yield total` is what your panels produced

#### Grid consumption  
`Zonneplan Electricity consumption today` is what you used from the grid

#### Return to grid
`Zonneplan Electricity returned today` is what you returned to the grid

## Troubleshooting

If you run into issues during setup or when entries do not update anymore please increase logging and provide them when creating an issue.
Add `custom_components.zonneplan_one: debug` to the logger config in you `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.zonneplan_one: debug
```
