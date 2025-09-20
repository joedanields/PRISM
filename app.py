from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import threading
import time
import os

# Create Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///machines.db'  # Fixed: Use current directory
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Database Models
class Machine(db.Model):
    __tablename__ = 'machines'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    machine_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='normal')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'machine_type': self.machine_type,
            'description': self.description,
            'location': self.location,
            'status': self.status,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    sensor_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    is_anomaly = db.Column(db.Boolean, default=False)
    anomaly_score = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'machine_id': self.machine_id,
            'sensor_type': self.sensor_type,
            'value': self.value,
            'unit': self.unit,
            'is_anomaly': self.is_anomaly,
            'anomaly_score': self.anomaly_score,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class Alert(db.Model):
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    alert_type = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sensor_data = db.Column(db.Text)
    is_acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_by = db.Column(db.String(100))
    acknowledged_at = db.Column(db.DateTime)
    email_sent = db.Column(db.Boolean, default=False)
    sms_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'machine_id': self.machine_id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'title': self.title,
            'message': self.message,
            'sensor_data': json.loads(self.sensor_data) if self.sensor_data else None,
            'is_acknowledged': self.is_acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'email_sent': self.email_sent,
            'sms_sent': self.sms_sent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }

# Routes
@app.route('/')
def dashboard():
    """Main dashboard view"""
    machines = Machine.query.filter_by(is_active=True).all()
    recent_alerts = Alert.query.filter_by(is_acknowledged=False).order_by(Alert.created_at.desc()).limit(5).all()
    return render_template('dashboard.html', machines=machines, alerts=recent_alerts)

@app.route('/api/machines')
def api_machines():
    """Get all machines data"""
    machines = Machine.query.filter_by(is_active=True).all()
    return jsonify([machine.to_dict() for machine in machines])

@app.route('/api/machine/<int:machine_id>/latest')
def api_machine_latest(machine_id):
    """Get latest sensor readings for a machine"""
    latest_readings = {}
    machine = Machine.query.get_or_404(machine_id)
    
    # Get distinct sensor types for this machine
    sensor_types = db.session.query(SensorReading.sensor_type).filter_by(machine_id=machine_id).distinct().all()
    sensor_types = [s[0] for s in sensor_types]
    
    for sensor_type in sensor_types:
        reading = SensorReading.query.filter_by(
            machine_id=machine_id, 
            sensor_type=sensor_type
        ).order_by(SensorReading.timestamp.desc()).first()
        
        if reading:
            latest_readings[sensor_type] = reading.to_dict()
    
    return jsonify({
        'machine': machine.to_dict(),
        'readings': latest_readings,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/machine/<int:machine_id>/mode', methods=['POST'])
def api_set_machine_mode(machine_id):
    """Set machine operation mode (normal/maintenance/sabotage)"""
    data = request.get_json()
    mode = data.get('mode', 'normal')
    
    machine = Machine.query.get_or_404(machine_id)
    machine.status = mode
    machine.updated_at = datetime.utcnow()
    
    # Create alert for mode change
    alert = Alert(
        machine_id=machine.id,
        alert_type='info',
        severity='low',
        title=f'Mode Change: {machine.name}',
        message=f'Machine mode changed to {mode.upper()}',
        sensor_data=json.dumps({'mode': mode, 'timestamp': datetime.now().isoformat()})
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'machine_id': machine_id,
        'new_mode': mode,
        'message': f'Machine {machine.name} set to {mode} mode'
    })

@app.route('/api/alerts')
def api_alerts():
    """Get recent alerts"""
    alerts = Alert.query.order_by(Alert.created_at.desc()).limit(20).all()
    return jsonify([alert.to_dict() for alert in alerts])

# Data Generation Functions
import random

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
        base_value = random.uniform(normal_min, normal_max)
        noise = random.uniform(-0.02, 0.02) * base_value
        return max(min_val, min(max_val, base_value + noise))
    
    elif machine_status == 'maintenance':
        base_value = random.uniform(normal_min, normal_max)
        if random.random() < 0.4:
            deviation = random.uniform(0.15, 0.35) * (normal_max - normal_min)
            base_value += random.choice([-deviation, deviation])
        return max(min_val, min(max_val, base_value))
    
    elif machine_status == 'sabotage':
        if random.random() < 0.8:
            if random.random() < 0.5:
                return random.uniform(max_val * 0.85, max_val)
            else:
                return random.uniform(min_val, min_val + (max_val - min_val) * 0.15)
        else:
            return random.uniform(normal_min, normal_max)
    
    return random.uniform(normal_min, normal_max)

def detect_simple_anomaly(value, sensor_config, machine_status):
    """Simple rule-based anomaly detection"""
    normal_min, normal_max = sensor_config['normal_range']
    
    if value < normal_min:
        deviation = (normal_min - value) / (normal_max - normal_min)
    elif value > normal_max:
        deviation = (value - normal_max) / (normal_max - normal_min)
    else:
        deviation = 0
    
    is_anomaly = deviation > 0.1
    anomaly_score = min(1.0, deviation)
    
    if machine_status == 'sabotage':
        if value >= sensor_config['max'] * 0.9 or value <= sensor_config['min'] * 1.1:
            is_anomaly = True
            anomaly_score = 0.95
    
    return is_anomaly, anomaly_score

def generate_machine_data(machine):
    """Generate all sensor readings for a specific machine"""
    machine_config = MACHINES_CONFIG.get(machine.machine_type)
    if not machine_config:
        return
    
    current_time = datetime.utcnow()
    critical_anomalies = []
    
    for sensor_type, sensor_config in machine_config['sensors'].items():
        value = generate_sensor_value(sensor_type, sensor_config, machine.status)
        is_anomaly, anomaly_score = detect_simple_anomaly(value, sensor_config, machine.status)
        
        if is_anomaly and anomaly_score > 0.8:
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
        
        db.session.add(reading)
    
    try:
        db.session.commit()
        
        # Generate critical alerts
        if critical_anomalies and machine.status != 'shutdown':
            alert = Alert(
                machine_id=machine.id,
                alert_type='critical',
                severity='critical',
                title=f'🚨 CRITICAL: {machine.name} Emergency!',
                message=f'EMERGENCY: Critical sensor anomalies detected! Sensors: {", ".join([f"{s}={v:.1f}{u}" for s,v,u in critical_anomalies])}. IMMEDIATE ACTION REQUIRED!',
                sensor_data=json.dumps([{'sensor': s, 'value': v, 'unit': u} for s,v,u in critical_anomalies])
            )
            db.session.add(alert)
            db.session.commit()
            
            print(f"🚨 CRITICAL ALERT: {machine.name} - Emergency detected!")
            
    except Exception as e:
        print(f"❌ Error saving readings: {e}")
        db.session.rollback()

def start_data_generation():
    """Main data generation loop"""
    print("🚀 Starting real-time sensor data generation...")
    generation_count = 0
    
    while True:
        try:
            with app.app_context():
                machines = Machine.query.filter_by(is_active=True).all()
                
                for machine in machines:
                    if machine.status != 'shutdown':
                        generate_machine_data(machine)
                
                generation_count += 1
                
                if generation_count % 10 == 0:
                    current_time = datetime.now().strftime('%H:%M:%S')
                    print(f"📊 [{current_time}] Generated {generation_count} data cycles for {len(machines)} machines")
                    
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
        
        time.sleep(3)

def create_tables():
    """Create database tables and sample data"""
    print("🔧 Creating database tables...")
    
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully!")
        
        # Add sample machines if none exist
        if Machine.query.count() == 0:
            machines_data = [
                {
                    'name': 'Chemical Reactor R-001',
                    'machine_type': 'Chemical Reactor',
                    'description': 'High-pressure chemical synthesis reactor for pharmaceutical production',
                    'location': 'Building A - Floor 2'
                },
                {
                    'name': 'Biotech Fermenter F-003', 
                    'machine_type': 'Biotech Fermenter',
                    'description': 'Industrial fermentation bioreactor for enzyme production',
                    'location': 'Building B - Floor 1'
                },
                {
                    'name': 'Distillation Column D-002',
                    'machine_type': 'Distillation Column', 
                    'description': 'Multi-stage distillation separation unit for solvent recovery',
                    'location': 'Building A - Floor 3'
                }
            ]
            
            for machine_data in machines_data:
                machine = Machine(**machine_data)
                db.session.add(machine)
            
            db.session.commit()
            print("✅ Sample machines added to database")

if __name__ == '__main__':
    create_tables()
    
    # Start background data generation
    data_thread = threading.Thread(target=start_data_generation, daemon=True)
    data_thread.start()
    
    print("🚀 Starting Predictive Maintenance Dashboard...")
    print("📊 Dashboard available at: http://localhost:5000")
    app.run(debug=True, threaded=True, port=5000)
