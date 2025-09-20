import random
import time
import json
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import app components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Machine configurations with realistic sensor ranges
MACHINES_CONFIG = {
    "Chemical Reactor": {
        "sensors": {
            "temperature": {"min": 200, "max": 800, "unit": "°C", "normal_range": [250, 400]},
            "pressure": {"min": 1, "max": 50, "unit": "bar", "normal_range": [10, 30]}, 
            "flow_rate": {"min": 5, "max": 100, "unit": "L/min", "normal_range": [20, 80]},
            "level": {"min": 0, "max": 215, "unit": "mm", "normal_range": [50, 180]}
        }
    },
    "Biotech Fermenter": {
        "sensors": {
            "temperature": {"min": 20, "max": 60, "unit": "°C", "normal_range": [35, 42]},
            "ph": {"min": 5.0, "max": 9.0, "unit": "pH", "normal_range": [6.5, 7.5]},
            "dissolved_oxygen": {"min": 0, "max": 100, "unit": "%", "normal_range": [20, 80]},
            "agitation": {"min": 50, "max": 500, "unit": "RPM", "normal_range": [100, 300]}
        }
    },
    "Distillation Column": {
        "sensors": {
            "temperature_top": {"min": 50, "max": 200, "unit": "°C", "normal_range": [80, 120]},
            "temperature_bottom": {"min": 100, "max": 300, "unit": "°C", "normal_range": [150, 250]},
            "pressure": {"min": 0.1, "max": 5.0, "unit": "bar", "normal_range": [0.5, 2.0]},
            "reflux_ratio": {"min": 1, "max": 10, "unit": "ratio", "normal_range": [2, 6]}
        }
    }
}

def generate_sensor_value(sensor_type, sensor_config, machine_status='normal'):
    """Generate realistic sensor values based on machine status"""
    min_val = sensor_config['min']
    max_val = sensor_config['max']
    normal_min, normal_max = sensor_config['normal_range']

    if machine_status == 'normal':
        # Normal operation with small random variations
        base_value = random.uniform(normal_min, normal_max)
        noise = random.uniform(-0.02, 0.02) * base_value  # 2% noise
        return max(min_val, min(max_val, base_value + noise))

    elif machine_status == 'maintenance':
        # Slightly irregular but not dangerous values
        base_value = random.uniform(normal_min, normal_max)
        if random.random() < 0.4:  # 40% chance of irregular reading
            deviation = random.uniform(0.15, 0.35) * (normal_max - normal_min)
            base_value += random.choice([-deviation, deviation])
        return max(min_val, min(max_val, base_value))

    elif machine_status == 'sabotage':
        # Extreme dangerous values
        if random.random() < 0.8:  # 80% chance of extreme reading
            if random.random() < 0.5:
                return random.uniform(max_val * 0.85, max_val)  # Near maximum (dangerous!)
            else:
                return random.uniform(min_val, min_val + (max_val - min_val) * 0.15)  # Near minimum
        else:
            return random.uniform(normal_min, normal_max)

    elif machine_status == 'shutdown':
        # All values drop to safe minimum levels
        return min_val + (max_val - min_val) * 0.05

    return random.uniform(normal_min, normal_max)

def detect_simple_anomaly(value, sensor_config, machine_status):
    """Simple rule-based anomaly detection"""
    normal_min, normal_max = sensor_config['normal_range']

    # Calculate how far outside normal range
    if value < normal_min:
        deviation = (normal_min - value) / (normal_max - normal_min)
    elif value > normal_max:
        deviation = (value - normal_max) / (normal_max - normal_min)
    else:
        deviation = 0

    # Determine if anomaly based on deviation
    is_anomaly = deviation > 0.1  # 10% outside normal range
    anomaly_score = min(1.0, deviation)

    # Special cases for sabotage mode
    if machine_status == 'sabotage':
        if value >= sensor_config['max'] * 0.9 or value <= sensor_config['min'] * 1.1:
            is_anomaly = True
            anomaly_score = 0.95

    return is_anomaly, anomaly_score

def generate_machine_data(machine):
    """Generate all sensor readings for a specific machine"""
    machine_config = MACHINES_CONFIG.get(machine.machine_type)
    if not machine_config:
        print(f"⚠️  No configuration found for machine type: {machine.machine_type}")
        return

    readings = []
    current_time = datetime.utcnow()

    # Import here to avoid circular imports
    from app import db
    from models.database import SensorReading, Alert

    anomaly_count = 0
    critical_anomalies = []

    for sensor_type, sensor_config in machine_config['sensors'].items():
        value = generate_sensor_value(sensor_type, sensor_config, machine.status)

        # Detect anomalies
        is_anomaly, anomaly_score = detect_simple_anomaly(value, sensor_config, machine.status)

        if is_anomaly:
            anomaly_count += 1
            if anomaly_score > 0.8:
                critical_anomalies.append((sensor_type, value, sensor_config['unit']))

        reading = SensorReading(
            machine_id=machine.id,
            sensor_type=sensor_type,
            value=round(value, 2),
            unit=sensor_config['unit'],
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 3),
            timestamp=current_time
        )

        readings.append(reading)
        db.session.add(reading)

    try:
        db.session.commit()

        # Generate alerts for anomalies
        if critical_anomalies and machine.status != 'shutdown':
            generate_alert(machine, critical_anomalies, 'critical')
        elif anomaly_count >= 2 and machine.status == 'maintenance':
            generate_alert(machine, [(r.sensor_type, r.value, r.unit) for r in readings if r.is_anomaly], 'warning')

    except Exception as e:
        print(f"❌ Error saving readings: {e}")
        db.session.rollback()

def generate_alert(machine, anomalous_readings, alert_level):
    """Generate alerts based on sensor readings"""
    from app import db
    from models.database import Alert

    if alert_level == 'critical':
        alert = Alert(
            machine_id=machine.id,
            alert_type='critical',
            severity='critical',
            title=f'🚨 CRITICAL: {machine.name} Emergency!',
            message=f'EMERGENCY: Critical sensor anomalies detected! Sensors: {", ".join([f"{s}={v:.1f}{u}" for s,v,u in anomalous_readings])}. IMMEDIATE ACTION REQUIRED!',
            sensor_data=json.dumps([{'sensor': s, 'value': v, 'unit': u} for s,v,u in anomalous_readings])
        )

        # Trigger emergency protocols
        if machine.status != 'shutdown':
            print(f"🚨 CRITICAL ALERT: {machine.name} - Emergency shutdown recommended!")

    elif alert_level == 'warning':
        alert = Alert(
            machine_id=machine.id,
            alert_type='warning',
            severity='medium',
            title=f'⚠️  WARNING: {machine.name} Needs Attention',
            message=f'Multiple irregular readings detected. Recommend maintenance inspection. Affected sensors: {len(anomalous_readings)}',
            sensor_data=json.dumps([{'sensor': s, 'value': v, 'unit': u} for s,v,u in anomalous_readings])
        )

    try:
        db.session.add(alert)
        db.session.commit()
    except Exception as e:
        print(f"❌ Error creating alert: {e}")
        db.session.rollback()

def start_data_generation():
    """Main data generation loop - runs continuously in background"""
    print("🚀 Starting real-time sensor data generation...")
    print("📊 Generating data every 3 seconds for all active machines...")

    generation_count = 0

    while True:
        try:
            # Import app context
            from app import app, db
            from models.database import Machine

            with app.app_context():
                machines = Machine.query.filter_by(is_active=True).all()

                if not machines:
                    print("⚠️  No active machines found. Waiting...")
                    time.sleep(5)
                    continue

                for machine in machines:
                    if machine.status != 'shutdown':
                        generate_machine_data(machine)

                generation_count += 1
                current_time = datetime.now().strftime('%H:%M:%S')

                # Status update every 10 generations (30 seconds)
                if generation_count % 10 == 0:
                    print(f"📊 [{current_time}] Generated {generation_count} data cycles for {len(machines)} machines")

                    # Show machine statuses
                    for machine in machines:
                        status_emoji = {
                            'normal': '✅',
                            'maintenance': '🔧', 
                            'sabotage': '🚨',
                            'shutdown': '⏹️'
                        }.get(machine.status, '❓')
                        print(f"   {status_emoji} {machine.name}: {machine.status}")

        except Exception as e:
            print(f"❌ Error in data generation: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(1)  # Generate data every 3 seconds

if __name__ == "__main__":
    start_data_generation()
