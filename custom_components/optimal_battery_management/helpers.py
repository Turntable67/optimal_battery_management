from datetime import datetime

def calculate_optimal_times_with_depreciation(forecast, current_capacity, max_capacity, charge_rate, discharge_rate, depreciation_per_kwh):
    """Calculate optimal charge and discharge times considering depreciation."""
    optimal_schedule = []
    for item in forecast:
        time = datetime.fromisoformat(item['datetime'])
        price = item['electricity_price'] / 1e7
        min_price_diff = depreciation_per_kwh

        if price < 0.2 and current_capacity < max_capacity:
            optimal_schedule.append({"action": "charge", "time": time, "price": price})
            current_capacity += charge_rate
        elif price > (0.2 + min_price_diff) and current_capacity > 0:
            optimal_schedule.append({"action": "discharge", "time": time, "price": price})
            current_capacity -= discharge_rate

    return optimal_schedule
