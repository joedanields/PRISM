from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Machine(db.Model):
    """Machine configuration and metadata"""

    __tablename__ = 'machines'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    machine_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='normal')  # normal, maintenance, sabotage, shutdown
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
    """Individual sensor readings from machines"""

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
    """System alerts and notifications"""

    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    alert_type = db.Column(db.String(30), nullable=False)  # warning, critical, maintenance, info
    severity = db.Column(db.String(20), nullable=False)  # low, medium, high, critical
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sensor_data = db.Column(db.Text)  # JSON string
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
