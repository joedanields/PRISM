from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import threading
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

# Create Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///machines.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# RATE LIMITING GLOBAL VARIABLES - FIXES EMAIL SPAM ISSUE
sent_maintenance_emails = set()
sent_sabotage_emails = set()
sent_twilio_calls = set()

# Email Configuration
class EmailConfig:
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587

    # REPLACE WITH YOUR GMAIL CREDENTIALS
    EMAIL_USER = 'joedanielajd@gmail.com'        # Your Gmail address
    EMAIL_PASSWORD = 'qdmo qlmy debz otzs'      # Gmail App Password (16 chars)

    # Recipients for different alert types (for demo, use your own email)
    MAINTENANCE_TEAM = 'swarnalathika11035@gmail.com'  # FIXED SYNTAX ERROR
    PLANT_MANAGER = 'stephenmerlyn5@gmail.com'
    EMERGENCY_RESPONSE = 'calebkclas@gmail.com'

# Enhanced Email Service
class EnhancedEmailService:
    def __init__(self):
        self.config = EmailConfig()

    def send_email_async(self, to_emails, subject, html_body, priority='normal'):
        """Send email asynchronously with priority levels"""
        def send():
            try:
                self._send_email(to_emails, subject, html_body, priority)
                print(f"✅ Email sent successfully to {to_emails}")
            except Exception as e:
                print(f"❌ Failed to send email: {str(e)}")

        threading.Thread(target=send, daemon=True).start()

    def _send_email(self, to_emails, subject, html_body, priority='normal'):
        """Internal method to send email via SMTP"""
        if isinstance(to_emails, str):
            to_emails = [to_emails]

        msg = MIMEMultipart('alternative')
        msg['From'] = self.config.EMAIL_USER
        msg['To'] = ', '.join(to_emails)
        msg['Subject'] = subject

        # Add priority headers for critical alerts
        if priority == 'critical':
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
            msg['Importance'] = 'High'

        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)

        with smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT) as server:
            server.starttls()
            server.login(self.config.EMAIL_USER, self.config.EMAIL_PASSWORD)
            server.send_message(msg)

    def send_irregular_readings_alert(self, machine, irregular_sensors, reading_history):
        """Send alert for irregular sensor readings (maintenance mode)"""
        subject = f"⚠️ Irregular Readings Detected - {machine.name} - Maintenance Required"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 700px; margin: 0 auto; background: #f8fafc; }}
                .container {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 25px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 26px; }}
                .alert-badge {{ background: #fef3c7; color: #92400e; padding: 12px; text-align: center; font-weight: bold; }}
                .content {{ padding: 25px; }}
                .machine-info {{ background: #fffbeb; border-left: 5px solid #f59e0b; padding: 20px; margin: 20px 0; border-radius: 8px; }}
                .readings-section {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin: 20px 0; }}
                .sensor-reading {{ display: flex; justify-content: space-between; align-items: center; padding: 12px; margin: 8px 0; background: white; border-radius: 6px; border-left: 4px solid #f59e0b; }}
                .recommendations {{ background: #eff6ff; border-left: 5px solid #3b82f6; padding: 20px; margin: 20px 0; border-radius: 8px; }}
                .footer {{ background: #1f2937; color: white; padding: 20px; text-align: center; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #f59e0b; color: white; text-decoration: none; border-radius: 8px; margin: 10px 5px; font-weight: bold; }}
                .status-warning {{ color: #d97706; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="alert-badge">
                    ⚠️ MAINTENANCE ALERT - Irregular Sensor Readings Detected
                </div>

                <div class="header">
                    <h1>Maintenance Required</h1>
                    <p>Predictive Maintenance System Alert</p>
                </div>

                <div class="content">
                    <div class="machine-info">
                        <h3>🏭 Equipment Information</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                            <div>
                                <p><strong>Machine:</strong> {machine.name}</p>
                                <p><strong>Type:</strong> {machine.machine_type}</p>
                            </div>
                            <div>
                                <p><strong>Location:</strong> {machine.location or 'Not specified'}</p>
                                <p><strong>Alert Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                            </div>
                        </div>
                        <p><strong>Current Status:</strong> <span class="status-warning">MAINTENANCE REQUIRED</span></p>
                    </div>

                    <div class="readings-section">
                        <h3>📊 Irregular Sensor Readings</h3>
                        <p style="color: #6b7280; margin-bottom: 15px;">The following sensors are showing readings outside normal operating parameters:</p>

                        {self._format_irregular_sensors(irregular_sensors)}
                    </div>

                    <div class="recommendations">
                        <h3>🔧 Recommended Actions</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                            <div>
                                <h4>Immediate Actions (0-4 hours):</h4>
                                <ul>
                                    <li>Verify sensor calibration</li>
                                    <li>Check mechanical connections</li>
                                    <li>Monitor readings closely</li>
                                    <li>Prepare maintenance tools</li>
                                </ul>
                            </div>
                            <div>
                                <h4>Scheduled Actions (24-48 hours):</h4>
                                <ul>
                                    <li>Schedule maintenance window</li>
                                    <li>Order replacement parts if needed</li>
                                    <li>Plan production shutdown</li>
                                    <li>Brief maintenance team</li>
                                </ul>
                            </div>
                        </div>

                        <div style="text-align: center; margin-top: 25px;">
                            <a href="http://localhost:5000/dashboard" class="btn">📊 View Live Dashboard</a>
                        </div>
                    </div>
                </div>

                <div class="footer">
                    <p><strong>Industrial Predictive Maintenance System</strong></p>
                    <p>Automated alert generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

        recipients = [self.config.MAINTENANCE_TEAM, self.config.PLANT_MANAGER]
        self.send_email_async(recipients, subject, html_body, priority='normal')

    def send_sabotage_incident_report(self, machine, incident_time, critical_sensors, pre_incident_data):
        """Send detailed sabotage incident report with historical data"""
        subject = f"🚨 CRITICAL INCIDENT REPORT - {machine.name} - {incident_time}"

        incident_id = f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; background: #fef2f2; }}
                .container {{ background: white; border: 3px solid #dc2626; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 30px rgba(220, 38, 38, 0.3); }}
                .emergency-header {{ background: #fef2f2; color: #dc2626; padding: 15px; text-align: center; font-weight: bold; font-size: 18px; border-bottom: 2px solid #dc2626; }}
                .header {{ background: linear-gradient(135deg, #dc2626, #991b1b); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }}
                .incident-id {{ background: rgba(255,255,255,0.2); padding: 10px; border-radius: 6px; margin-top: 15px; font-family: monospace; font-size: 16px; }}
                .content {{ padding: 30px; }}
                .incident-summary {{ background: #fef2f2; border: 2px solid #fca5a5; border-radius: 10px; padding: 25px; margin: 25px 0; }}
                .timeline-section {{ background: #f8fafc; border-radius: 10px; padding: 25px; margin: 25px 0; }}
                .timeline-item {{ border-left: 4px solid #dc2626; padding-left: 20px; margin: 15px 0; }}
                .critical-readings {{ background: #fff5f5; border: 2px solid #fca5a5; border-radius: 10px; padding: 20px; margin: 20px 0; }}
                .sensor-critical {{ background: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 10px 0; border-radius: 6px; }}
                .pre-incident-data {{ background: #fffbeb; border: 1px solid #fbbf24; border-radius: 10px; padding: 20px; margin: 20px 0; }}
                .data-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                .data-table th, .data-table td {{ border: 1px solid #e5e7eb; padding: 12px; text-align: center; }}
                .data-table th {{ background: #f9fafb; font-weight: bold; }}
                .emergency-actions {{ background: #dc2626; color: white; padding: 25px; margin: 25px 0; border-radius: 10px; }}
                .emergency-actions h3 {{ color: white; margin-top: 0; }}
                .footer {{ background: #1f2937; color: white; padding: 25px; text-align: center; }}
                .btn {{ display: inline-block; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 10px 5px; font-weight: bold; }}
                .btn-emergency {{ background: white; color: #dc2626; border: 2px solid #dc2626; }}
                .status-critical {{ color: #dc2626; font-weight: bold; font-size: 18px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="emergency-header">
                    🚨 CRITICAL INCIDENT ALERT - IMMEDIATE RESPONSE REQUIRED 🚨
                </div>

                <div class="header">
                    <h1>SABOTAGE INCIDENT DETECTED</h1>
                    <p>Emergency Response Protocol Activated</p>
                    <div class="incident-id">
                        <strong>INCIDENT ID: {incident_id}</strong>
                    </div>
                </div>

                <div class="content">
                    <div class="incident-summary">
                        <h3>🚨 Incident Summary</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                            <div>
                                <p><strong>Equipment:</strong> {machine.name}</p>
                                <p><strong>Type:</strong> {machine.machine_type}</p>
                                <p><strong>Location:</strong> {machine.location or 'Not specified'}</p>
                            </div>
                            <div>
                                <p><strong>Incident Time:</strong> {incident_time}</p>
                                <p><strong>Alert Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                                <p><strong>Severity:</strong> <span class="status-critical">CRITICAL</span></p>
                            </div>
                        </div>
                    </div>

                    <div class="timeline-section">
                        <h3>📅 Incident Timeline</h3>
                        <div class="timeline-item">
                            <p><strong>T-60 seconds:</strong> Normal operation parameters maintained</p>
                        </div>
                        <div class="timeline-item">
                            <p><strong>T-30 seconds:</strong> First sensor anomalies detected</p>
                        </div>
                        <div class="timeline-item">
                            <p><strong>T-0 seconds:</strong> Critical threshold breached - INCIDENT TRIGGERED</p>
                        </div>
                        <div class="timeline-item">
                            <p><strong>T+30 seconds:</strong> Alert email generated and sent</p>
                        </div>
                    </div>

                    <div class="critical-readings">
                        <h3>⚠️ Critical Sensor Readings at Incident Time</h3>
                        {self._format_critical_sensors(critical_sensors)}
                    </div>

                    <div class="pre-incident-data">
                        <h3>📊 Pre-Incident Data Analysis (1 minute before)</h3>
                        <p>Historical sensor data from 60 seconds before the incident for forensic analysis:</p>
                        {self._format_pre_incident_data(pre_incident_data)}
                    </div>

                    <div class="emergency-actions">
                        <h3>🎯 IMMEDIATE EMERGENCY ACTIONS</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px;">
                            <div>
                                <h4>Priority 1 (0-5 minutes):</h4>
                                <ul>
                                    <li><strong>EVACUATE</strong> all personnel from danger zone</li>
                                    <li><strong>ACTIVATE</strong> emergency shutdown procedures</li>
                                    <li><strong>SECURE</strong> the affected area</li>
                                    <li><strong>NOTIFY</strong> emergency services if required</li>
                                </ul>
                            </div>
                            <div>
                                <h4>Priority 2 (5-30 minutes):</h4>
                                <ul>
                                    <li><strong>DISPATCH</strong> emergency response team</li>
                                    <li><strong>ISOLATE</strong> electrical and fluid systems</li>
                                    <li><strong>DOCUMENT</strong> scene and readings</li>
                                    <li><strong>REPORT</strong> to plant management</li>
                                </ul>
                            </div>
                        </div>

                        <div style="text-align: center; margin-top: 30px;">
                            <a href="http://localhost:5000/dashboard" class="btn btn-emergency">🖥️ View Emergency Dashboard</a>
                            <a href="tel:+919876543210" class="btn btn-emergency">📞 Call Emergency Response</a>
                        </div>
                    </div>
                </div>

                <div class="footer">
                    <p><strong>🚨 CRITICAL INCIDENT REPORT - {incident_id}</strong></p>
                    <p>Generated by Industrial Predictive Maintenance System</p>
                    <p>Emergency Hotline: +91-9876543210</p>
                </div>
            </div>
        </body>
        </html>
        """

        recipients = [
            self.config.EMERGENCY_RESPONSE,
            self.config.PLANT_MANAGER,
            self.config.MAINTENANCE_TEAM
        ]
        self.send_email_async(recipients, subject, html_body, priority='critical')

        print(f"🚨 CRITICAL INCIDENT REPORT SENT - ID: {incident_id}")

    def _format_irregular_sensors(self, irregular_sensors):
        """Format irregular sensor data for maintenance email"""
        html = ""
        for sensor_type, reading in irregular_sensors.items():
            deviation = reading.get('anomaly_score', 0) * 100
            html += f'''
            <div class="sensor-reading">
                <div>
                    <strong>{sensor_type.replace('_', ' ').title()}</strong><br>
                    <small style="color: #6b7280;">Current: {reading.get('value', 'N/A')} {reading.get('unit', '')}</small>
                </div>
                <div style="text-align: right;">
                    <span style="background: #fbbf24; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                        {deviation:.1f}% deviation
                    </span>
                </div>
            </div>
            '''
        return html

    def _format_critical_sensors(self, critical_sensors):
        """Format critical sensor data for sabotage email"""
        html = ""
        for sensor_type, reading in critical_sensors.items():
            if reading.get('is_anomaly', False):
                risk_level = reading.get('anomaly_score', 0) * 100
                html += f'''
                <div class="sensor-critical">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="color: #dc2626;">{sensor_type.replace('_', ' ').title()}</strong><br>
                            <span style="font-size: 18px; font-weight: bold; color: #dc2626;">
                                {reading.get('value', 'N/A')} {reading.get('unit', '')}
                            </span><br>
                            <small style="color: #6b7280;">Normal range: {reading.get('normal_range', 'Not specified')}</small>
                        </div>
                        <div style="text-align: right;">
                            <span style="background: #dc2626; color: white; padding: 6px 12px; border-radius: 6px; font-weight: bold;">
                                {risk_level:.1f}% RISK
                            </span>
                        </div>
                    </div>
                </div>
                '''
        return html

    def _format_pre_incident_data(self, pre_incident_data):
        """Format pre-incident historical data table"""
        if not pre_incident_data:
            return "<p>Historical data not available</p>"

        html = '''
        <table class="data-table">
            <thead>
                <tr>
                    <th>Time (seconds before incident)</th>
                    <th>Sensor</th>
                    <th>Value</th>
                    <th>Status</th>
                    <th>Trend</th>
                </tr>
            </thead>
            <tbody>
        '''

        for entry in pre_incident_data[:10]:
            time_diff = entry.get('time_before_incident', 0)
            sensor = entry.get('sensor_type', 'Unknown')
            value = f"{entry.get('value', 'N/A')} {entry.get('unit', '')}"
            status = "🔴 Anomaly" if entry.get('is_anomaly') else "🟢 Normal"
            trend = entry.get('trend', '→')

            html += f'''
            <tr>
                <td>-{time_diff}s</td>
                <td>{sensor.replace('_', ' ').title()}</td>
                <td>{value}</td>
                <td>{status}</td>
                <td>{trend}</td>
            </tr>
            '''

        html += '''
            </tbody>
        </table>
        <p style="font-style: italic; color: #6b7280; margin-top: 10px;">
            * This historical data can be used for forensic analysis to determine the root cause of the incident
        </p>
        '''

        return html

# Initialize email service
enhanced_email_service = EnhancedEmailService()

# 3. TWILIO CONFIGURATION CLASS
class TwilioConfig:
    # Get these from https://console.twilio.com/
    ACCOUNT_SID = 'AC4d31a70036733a20a56c23cc23a9bdd2'          # Starts with 'AC'
    AUTH_TOKEN = '91faecc858aef6b3e6770e7e1e35e8a1'            # 32-character string
    TWILIO_PHONE_NUMBER = '+18783099377'              # Your Twilio phone number

    # Emergency contact numbers (for demo, use your own phone)
    EMERGENCY_CONTACTS = [
        '+91-7806984837',  # Plant Manager (replace with your number)
         '+91-7806984837',  # Maintenance Chief  
         '+91-7806984837',  # Emergency Response
    ]

    # Voice settings
    VOICE = 'alice'  # Options: alice, man, woman
    LANGUAGE = 'en-US'  # en-US, en-GB, etc.

# 4. TWILIO VOICE SERVICE CLASS
class TwilioVoiceService:
    def __init__(self):
        self.config = TwilioConfig()
        self.client = Client(self.config.ACCOUNT_SID, self.config.AUTH_TOKEN)

    def make_emergency_call(self, machine_name, incident_details, incident_time, severity='CRITICAL'):
        """Make emergency voice call with detailed incident information"""

        # Create professional emergency message
        message = self._create_emergency_message(machine_name, incident_details, incident_time, severity)

        # Create TwiML response for the call
        twiml_response = f'''<Response>
    <Say voice="{self.config.VOICE}" language="{self.config.LANGUAGE}">
        {message}
    </Say>
    <Pause length="2"/>
    <Say voice="{self.config.VOICE}" language="{self.config.LANGUAGE}">
        Press any key to acknowledge this emergency alert.
    </Say>
    <Gather timeout="10" numDigits="1">
        <Say voice="{self.config.VOICE}" language="{self.config.LANGUAGE}">
            Thank you for acknowledging. Emergency response team has been notified.
        </Say>
    </Gather>
    <Say voice="{self.config.VOICE}" language="{self.config.LANGUAGE}">
        If you did not acknowledge, this call will be logged as unattended. 
        Please check the emergency dashboard immediately.
    </Say>
</Response>'''

        # Call each emergency contact
        call_results = []

        for contact_number in self.config.EMERGENCY_CONTACTS:
            try:
                print(f"📞 Calling emergency contact: {contact_number}")

                call = self.client.calls.create(
                    twiml=twiml_response,
                    to=contact_number,
                    from_=self.config.TWILIO_PHONE_NUMBER,
                    timeout=30,
                    record=True  # Record the call for documentation
                )

                call_results.append({
                    'number': contact_number,
                    'call_sid': call.sid,
                    'status': 'initiated',
                    'message': f'Emergency call initiated to {contact_number}'
                })

                print(f"✅ Emergency call initiated - SID: {call.sid}")

                # Wait 5 seconds between calls to avoid overwhelming
                time.sleep(5)

            except Exception as e:
                print(f"❌ Failed to call {contact_number}: {str(e)}")
                call_results.append({
                    'number': contact_number,
                    'status': 'failed',
                    'error': str(e)
                })

        return call_results

    def send_emergency_sms_backup(self, machine_name, incident_details, incident_time):
        """Send SMS backup if calls are not answered"""

        sms_message = f'''🚨 CRITICAL EMERGENCY ALERT 🚨

INCIDENT: {machine_name} FAILURE
TIME: {incident_time}
DETAILS: {incident_details}

IMMEDIATE ACTION REQUIRED!
Check dashboard: http://localhost:5000/dashboard

This is an automated emergency alert from Industrial Predictive Maintenance System.'''

        sms_results = []

        for contact_number in self.config.EMERGENCY_CONTACTS:
            try:
                message = self.client.messages.create(
                    body=sms_message,
                    from_=self.config.TWILIO_PHONE_NUMBER,
                    to=contact_number
                )

                sms_results.append({
                    'number': contact_number,
                    'message_sid': message.sid,
                    'status': 'sent'
                })

                print(f"📱 Emergency SMS sent to {contact_number} - SID: {message.sid}")

            except Exception as e:
                print(f"❌ Failed to send SMS to {contact_number}: {str(e)}")
                sms_results.append({
                    'number': contact_number,
                    'status': 'failed',
                    'error': str(e)
                })

        return sms_results

    def make_maintenance_reminder_call(self, machine_name, maintenance_details):
        """Make friendly maintenance reminder call"""

        message = f'''Hello, this is a maintenance reminder from Industrial Plant Alpha. Equipment {machine_name} requires scheduled maintenance. Details: {maintenance_details}. Please schedule maintenance within the next 48 hours to ensure optimal performance. Thank you for maintaining industrial safety standards.'''

        twiml_response = f'''<Response>
    <Say voice="{self.config.VOICE}" language="{self.config.LANGUAGE}">
        {message}
    </Say>
</Response>'''

        # Call only the first contact for maintenance reminders
        contact_number = self.config.EMERGENCY_CONTACTS[0]

        try:
            call = self.client.calls.create(
                twiml=twiml_response,
                to=contact_number,
                from_=self.config.TWILIO_PHONE_NUMBER
            )

            print(f"📞 Maintenance reminder call sent - SID: {call.sid}")
            return {'status': 'success', 'call_sid': call.sid}

        except Exception as e:
            print(f"❌ Failed to make maintenance call: {str(e)}")
            return {'status': 'failed', 'error': str(e)}

    def _create_emergency_message(self, machine_name, incident_details, incident_time, severity):
        """Create professional emergency voice message"""

        return f'''ATTENTION! This is an emergency alert from Industrial Plant Alpha Predictive Maintenance System. We have detected a {severity} equipment failure. Affected Equipment: {machine_name}. Incident Time: {incident_time}. Incident Details: {incident_details}. Immediate emergency response is required. Please proceed to the plant emergency control center immediately. All safety protocols must be followed. This is not a drill. Repeat, this is not a drill.'''

    def get_call_status(self, call_sid):
        """Check the status of a specific call"""
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                'status': call.status,
                'duration': call.duration,
                'answered_by': call.answered_by,
                'start_time': str(call.start_time) if call.start_time else None,
                'end_time': str(call.end_time) if call.end_time else None
            }
        except Exception as e:
            return {'error': str(e)}

# 5. INITIALIZE TWILIO SERVICE (add this after your other initializations)
twilio_service = TwilioVoiceService()

# AI CHATBOT INTEGRATION FOR INDUSTRIAL PREDICTIVE MAINTENANCE
# Add these imports to your existing app.py

import openai
import json
from datetime import datetime, timedelta
import re
from typing import Dict, List, Any

# AI Chatbot Configuration
class ChatbotConfig:
    # You can use OpenAI API or run locally with Ollama
    USE_OPENAI = False  # Set to True if you have OpenAI API key
    OPENAI_API_KEY = "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"  # Replace with your key

    # For local AI (free alternative)
    USE_LOCAL_AI = True
    LOCAL_MODEL = "llama2"  # or "mistral", "codellama"

    # Chatbot personality
    SYSTEM_PROMPT = """You are MaintenanceBot, an expert AI assistant for Industrial Predictive Maintenance Systems.
    You help plant operators, maintenance teams, and managers with:
    - Equipment diagnostics and troubleshooting
    - Sensor reading analysis and anomaly detection
    - Maintenance scheduling and recommendations
    - Safety protocols and emergency procedures
    - System monitoring and alerts interpretation

    Always be professional, concise, and safety-focused. Use industrial terminology appropriately."""

# Enhanced Chatbot Service
class IndustrialChatbot:
    def __init__(self):
        self.config = ChatbotConfig()
        self.conversation_history = []

    def get_machine_context(self, machine_id=None):
        """Get current machine status for context"""
        try:
            if machine_id:
                machine = Machine.query.get(machine_id)
                if machine:
                    # Get latest readings
                    latest_readings = db.session.query(SensorReading).filter_by(
                        machine_id=machine_id
                    ).order_by(SensorReading.timestamp.desc()).limit(10).all()

                    context = {
                        'machine_name': machine.name,
                        'machine_type': machine.machine_type,
                        'status': machine.status,
                        'location': machine.location,
                        'latest_readings': [r.to_dict() for r in latest_readings]
                    }
                    return context
            else:
                # Get all machines overview
                machines = Machine.query.filter_by(is_active=True).all()
                alerts = Alert.query.filter_by(is_acknowledged=False).limit(5).all()

                context = {
                    'total_machines': len(machines),
                    'machines': [m.to_dict() for m in machines],
                    'active_alerts': [a.to_dict() for a in alerts]
                }
                return context

        except Exception as e:
            print(f"Error getting machine context: {e}")
            return {}

    def analyze_query_intent(self, message: str) -> Dict[str, Any]:
        """Analyze user query to understand intent"""
        message_lower = message.lower()

        # Extract machine mentions
        machine_patterns = [
            r'reactor|r-001|chemical reactor',
            r'fermenter|f-003|biotech fermenter', 
            r'column|d-002|distillation',
            r'exchanger|hx-005|heat exchanger'
        ]

        mentioned_machines = []
        for i, pattern in enumerate(machine_patterns):
            if re.search(pattern, message_lower):
                machine_ids = [1, 2, 3, 4]  # Corresponding to your 4 machines
                mentioned_machines.append(machine_ids[i])

        # Intent detection
        intents = {
            'machine_status': any(word in message_lower for word in ['status', 'condition', 'how is', 'state']),
            'troubleshooting': any(word in message_lower for word in ['problem', 'issue', 'error', 'fault', 'broken', 'fix']),
            'maintenance': any(word in message_lower for word in ['maintenance', 'repair', 'schedule', 'service']),
            'anomaly_analysis': any(word in message_lower for word in ['anomaly', 'abnormal', 'unusual', 'readings']),
            'safety': any(word in message_lower for word in ['safety', 'emergency', 'danger', 'evacuation']),
            'predictions': any(word in message_lower for word in ['predict', 'forecast', 'future', 'when will']),
            'general_help': any(word in message_lower for word in ['help', 'how to', 'guide', 'tutorial'])
        }

        # Determine primary intent
        primary_intent = max(intents, key=intents.get) if any(intents.values()) else 'general_help'

        return {
            'primary_intent': primary_intent,
            'mentioned_machines': mentioned_machines,
            'intents': intents,
            'original_message': message
        }

    def generate_contextual_response(self, query_analysis: Dict, machine_context: Dict) -> str:
        """Generate intelligent response based on context"""
        intent = query_analysis['primary_intent']
        machines = query_analysis['mentioned_machines']

        if intent == 'machine_status':
            return self._handle_status_query(machines, machine_context)
        elif intent == 'troubleshooting':
            return self._handle_troubleshooting(machines, machine_context)
        elif intent == 'maintenance':
            return self._handle_maintenance_query(machines, machine_context)
        elif intent == 'anomaly_analysis':
            return self._handle_anomaly_analysis(machines, machine_context)
        elif intent == 'safety':
            return self._handle_safety_query(machines, machine_context)
        elif intent == 'predictions':
            return self._handle_prediction_query(machines, machine_context)
        else:
            return self._handle_general_help()

    def _handle_status_query(self, machines: List[int], context: Dict) -> str:
        """Handle machine status queries"""
        if machines:
            machine_id = machines[0]
            machine = Machine.query.get(machine_id)
            if machine:
                latest_reading = SensorReading.query.filter_by(machine_id=machine_id).order_by(SensorReading.timestamp.desc()).first()

                status_emoji = {"normal": "🟢", "maintenance": "🟡", "sabotage": "🔴", "shutdown": "⚫"}

                response = f"""**{machine.name} Status Report** {status_emoji.get(machine.status, "⚪")}

📊 **Current Status:** {machine.status.upper()}
📍 **Location:** {machine.location}
⏰ **Last Update:** {latest_reading.timestamp.strftime('%Y-%m-%d %H:%M:%S') if latest_reading else 'No data'}

"""
                if latest_reading:
                    if latest_reading.is_anomaly:
                        response += f"⚠️ **Alert:** Anomaly detected in {latest_reading.sensor_type} (Score: {latest_reading.anomaly_score:.2f})"
                    else:
                        response += f"✅ **Sensors:** Operating within normal parameters"

                return response
        else:
            # Overall system status
            total_machines = Machine.query.count()
            normal_machines = Machine.query.filter_by(status='normal').count()
            maintenance_machines = Machine.query.filter_by(status='maintenance').count()
            critical_machines = Machine.query.filter_by(status='sabotage').count()

            return f"""**Industrial Plant Alpha - System Overview**

🏭 **Total Machines:** {total_machines}
🟢 **Normal Operation:** {normal_machines}
🟡 **Maintenance Required:** {maintenance_machines}  
🔴 **Critical Issues:** {critical_machines}

Type 'help' for available commands or ask about specific machines."""

    def _handle_troubleshooting(self, machines: List[int], context: Dict) -> str:
        """Handle troubleshooting queries"""
        if machines:
            machine_id = machines[0]
            machine = Machine.query.get(machine_id)

            # Get recent anomalies
            anomalies = SensorReading.query.filter(
                SensorReading.machine_id == machine_id,
                SensorReading.is_anomaly == True
            ).order_by(SensorReading.timestamp.desc()).limit(5).all()

            if anomalies:
                response = f"""**🔧 Troubleshooting Guide: {machine.name}**

**Recent Anomalies Detected:**
"""
                for anomaly in anomalies:
                    response += f"• {anomaly.sensor_type}: {anomaly.value} {anomaly.unit} (Risk: {anomaly.anomaly_score:.0%})\n"

                response += """
**Recommended Actions:**
1. 🔍 Inspect sensor calibration
2. 🔧 Check mechanical connections  
3. 📊 Monitor trending patterns
4. 📋 Review maintenance logs
5. ☎️ Contact maintenance team if issues persist

Need specific sensor troubleshooting? Ask me about the sensor type."""

                return response
            else:
                return f"✅ **{machine.name}** is currently operating normally with no anomalies detected."

        return """**🔧 General Troubleshooting Steps:**

1. **Identify the Problem** - What symptoms are you observing?
2. **Check System Status** - Ask me about specific machine status
3. **Review Recent Alerts** - Look for patterns in anomalies  
4. **Follow Safety Protocols** - Ensure personnel safety first
5. **Document Issues** - Record all observations for analysis

Which machine or sensor needs troubleshooting?"""

    def _handle_maintenance_query(self, machines: List[int], context: Dict) -> str:
        """Handle maintenance-related queries"""
        return f"""**🔧 Maintenance Management Guide**

**Preventive Maintenance Schedule:**
• **Daily:** Visual inspections, sensor readings check
• **Weekly:** Lubrication, belt tension, vibration analysis  
• **Monthly:** Calibration verification, filter replacement
• **Quarterly:** Comprehensive system diagnostics

**Maintenance Priorities:**
1. 🔴 **Critical Issues** - Immediate attention required
2. 🟡 **Scheduled Maintenance** - Within 48 hours
3. 🟢 **Preventive Tasks** - Next maintenance window

**Need to schedule maintenance?** 
- Check machine status first
- Use emergency contacts for critical issues
- Document all maintenance activities

Which machine needs maintenance assessment?"""

    def _handle_anomaly_analysis(self, machines: List[int], context: Dict) -> str:
        """Handle anomaly analysis queries"""
        if machines:
            machine_id = machines[0]
            # Get recent readings for analysis
            readings = SensorReading.query.filter_by(machine_id=machine_id).order_by(SensorReading.timestamp.desc()).limit(20).all()

            anomaly_count = sum(1 for r in readings if r.is_anomaly)
            avg_score = sum(r.anomaly_score for r in readings) / len(readings) if readings else 0

            return f"""**📊 Anomaly Analysis Report**

**Machine:** {Machine.query.get(machine_id).name if Machine.query.get(machine_id) else 'Unknown'}
**Analysis Period:** Last 20 readings

📈 **Anomaly Rate:** {anomaly_count}/20 readings ({anomaly_count/20*100:.1f}%)
⚠️ **Average Risk Score:** {avg_score:.2f}

**Risk Assessment:**
• Score < 0.3: Normal operation
• Score 0.3-0.7: Monitor closely  
• Score > 0.7: Immediate attention required

**Trending:** {'📈 Increasing' if avg_score > 0.5 else '📉 Stable' if avg_score > 0.3 else '✅ Normal'}"""

        return """**📊 Anomaly Detection System**

Our AI continuously monitors sensor readings and detects:
• **Temperature variations** beyond normal ranges
• **Pressure fluctuations** indicating potential issues
• **Flow rate anomalies** suggesting blockages
• **Vibration patterns** indicating mechanical problems

**Anomaly Scoring:**
- 0.0-0.3: Normal operation 🟢
- 0.3-0.7: Attention needed 🟡  
- 0.7-1.0: Critical issue 🔴

Which machine's anomalies would you like to analyze?"""

    def _handle_safety_query(self, machines: List[int], context: Dict) -> str:
        """Handle safety-related queries"""
        return """**🚨 INDUSTRIAL SAFETY PROTOCOLS**

**EMERGENCY PROCEDURES:**
1. **Immediate Evacuation** - Clear danger zone
2. **Emergency Shutdown** - Activate safety systems
3. **Alert Emergency Team** - Call +91-7806984837
4. **Secure Area** - Prevent unauthorized access

**DAILY SAFETY CHECKLIST:**
✅ Personal Protective Equipment (PPE) inspection
✅ Emergency exit routes clear
✅ Safety systems functional
✅ Hazardous material containment secure

**CRITICAL SAFETY ALERTS:**
• Temperature > 700°C: Immediate evacuation
• Pressure > 45 bar: Emergency shutdown
• Gas leak detection: Activate ventilation

**Emergency Contacts:**
📞 Plant Manager: +91-7806984837
📧 Emergency Response: calebkclas@gmail.com

**Remember: SAFETY FIRST - When in doubt, evacuate and call for help!**"""

    def _handle_prediction_query(self, machines: List[int], context: Dict) -> str:
        """Handle predictive analysis queries"""
        return """**🔮 Predictive Maintenance Insights**

**Our AI Predicts:**
• **Equipment Failures** - 2-7 days advance warning
• **Maintenance Needs** - Optimal scheduling recommendations  
• **Performance Degradation** - Efficiency decline patterns
• **Component Wear** - Replacement timing predictions

**Prediction Accuracy:**
• Temperature sensors: 94% accuracy
• Pressure monitoring: 91% accuracy  
• Flow rate analysis: 89% accuracy
• Overall system health: 92% accuracy

**Current Predictions:**
Based on recent sensor data, our models suggest:
- Routine maintenance recommended for optimal performance
- No critical failures predicted in next 7 days
- Monitor temperature trends in Chemical Reactor

**Want specific predictions?** Ask about individual machines or sensors."""

    def _handle_general_help(self) -> str:
        """Provide general help and available commands"""
        return """**🤖 MaintenanceBot - Your AI Assistant**

**I can help you with:**

🏭 **Machine Status**
- "What's the status of Chemical Reactor?"  
- "Show me all machine conditions"

🔧 **Troubleshooting**
- "Reactor R-001 has issues"
- "How to fix high temperature alerts?"

📅 **Maintenance**
- "When is next maintenance due?"
- "Maintenance checklist for Fermenter F-003"

⚠️ **Anomaly Analysis** 
- "Analyze recent anomalies"
- "Why is pressure sensor showing alerts?"

🚨 **Safety & Emergency**
- "Emergency procedures"  
- "Safety protocols for high pressure"

📊 **Predictions**
- "Predict equipment failures"
- "Maintenance forecasting"

**Example Questions:**
• "Status of all machines"
• "Troubleshoot Chemical Reactor R-001"  
• "Safety procedures for emergency"
• "Predict next maintenance window"

**Just ask naturally - I understand industrial terminology!**"""

    def chat(self, message: str, user_id: str = "user", machine_id: int = None) -> Dict[str, Any]:
        """Main chat interface"""
        try:
            # Analyze query intent
            query_analysis = self.analyze_query_intent(message)

            # Get machine context
            machine_context = self.get_machine_context(machine_id)

            # Generate response
            response = self.generate_contextual_response(query_analysis, machine_context)

            # Store conversation
            conversation_entry = {
                'timestamp': datetime.now().isoformat(),
                'user_id': user_id,
                'message': message,
                'response': response,
                'intent': query_analysis['primary_intent'],
                'machine_context': bool(machine_id)
            }

            self.conversation_history.append(conversation_entry)

            return {
                'success': True,
                'response': response,
                'intent': query_analysis['primary_intent'],
                'suggested_actions': self._get_suggested_actions(query_analysis),
                'conversation_id': len(self.conversation_history)
            }

        except Exception as e:
            return {
                'success': False,
                'response': f"I apologize, but I encountered an error: {str(e)}. Please try rephrasing your question.",
                'error': str(e)
            }

    def _get_suggested_actions(self, query_analysis: Dict) -> List[str]:
        """Get suggested follow-up actions"""
        intent = query_analysis['primary_intent']

        suggestions = {
            'machine_status': [
                "View detailed sensor readings",
                "Check maintenance schedule",
                "Analyze recent anomalies"
            ],
            'troubleshooting': [
                "Contact maintenance team",
                "View troubleshooting guide",
                "Schedule diagnostic check"
            ],
            'maintenance': [
                "Schedule maintenance window",
                "View maintenance checklist",
                "Contact maintenance team"
            ],
            'safety': [
                "Review emergency procedures",
                "Test safety systems",
                "Update emergency contacts"
            ]
        }

        return suggestions.get(intent, ["Ask another question", "Get help", "Check system status"])

# Initialize the chatbot
industrial_chatbot = IndustrialChatbot()

# Flask routes for chatbot API
@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """Main chatbot API endpoint"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        user_id = data.get('user_id', 'anonymous')
        machine_id = data.get('machine_id', None)

        if not message.strip():
            return jsonify({
                'success': False,
                'error': 'Empty message'
            })

        # Get chatbot response
        response = industrial_chatbot.chat(message, user_id, machine_id)

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'response': "I apologize, but I'm having technical difficulties. Please try again."
        })

@app.route('/api/chat/suggestions')
def get_chat_suggestions():
    """Get suggested questions for the chatbot"""
    suggestions = [
        "What's the status of all machines?",
        "Troubleshoot Chemical Reactor R-001",
        "Show me maintenance schedule",  
        "Analyze recent anomalies",
        "Emergency safety procedures",
        "Predict next equipment failure",
        "Help with sensor calibration",
        "System performance overview"
    ]

    return jsonify({
        'success': True,
        'suggestions': suggestions
    })

@app.route('/api/chat/history/<user_id>')
def get_chat_history(user_id):
    """Get chat history for a user"""
    try:
        # Filter conversation history for specific user
        user_history = [
            conv for conv in industrial_chatbot.conversation_history 
            if conv.get('user_id') == user_id
        ]

        return jsonify({
            'success': True,
            'history': user_history[-20:]  # Last 20 conversations
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/chat')
def chat_interface():
    """Render chat interface page"""
    return render_template('chat.html')

# 6. ADD THESE NEW ROUTES TO YOUR FLASK APP

@app.route('/api/emergency-call/<int:machine_id>')
def trigger_emergency_call(machine_id):
    """Trigger emergency call for specific machine"""
    try:
        machine = Machine.query.get_or_404(machine_id)

        # Get latest critical readings
        latest_readings = db.session.query(SensorReading).filter_by(
            machine_id=machine_id
        ).order_by(SensorReading.timestamp.desc()).limit(4).all()

        # Format incident details
        critical_sensors = []
        for reading in latest_readings:
            if reading.is_anomaly and reading.anomaly_score > 0.8:
                critical_sensors.append(f"{reading.sensor_type}: {reading.value} {reading.unit}")

        incident_details = f"Multiple sensor failures detected. Critical readings: {', '.join(critical_sensors)}"
        incident_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Make emergency calls
        call_results = twilio_service.make_emergency_call(
            machine_name=machine.name,
            incident_details=incident_details,
            incident_time=incident_time,
            severity='CRITICAL'
        )

        # Also send SMS backup after 30 seconds
        def send_sms_backup():
            time.sleep(30)  # Wait 30 seconds
            twilio_service.send_emergency_sms_backup(
                machine_name=machine.name,
                incident_details=incident_details,
                incident_time=incident_time
            )

        threading.Thread(target=send_sms_backup, daemon=True).start()

        return jsonify({
            'success': True,
            'message': f'Emergency calls initiated for {machine.name}',
            'call_results': call_results,
            'incident_time': incident_time
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/debug/test-call/<call_type>')
def test_call(call_type):
    """Test Twilio calling functionality"""
    try:
        machine = Machine.query.first()
        if not machine:
            return jsonify({'error': 'No machines found'})

        if call_type == 'emergency':
            call_results = twilio_service.make_emergency_call(
                machine_name=machine.name,
                incident_details="TEST: Critical temperature and pressure anomalies detected",
                incident_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                severity='CRITICAL'
            )
            return jsonify({
                'success': True, 
                'message': 'Test emergency call initiated',
                'call_results': call_results
            })

        elif call_type == 'maintenance':
            call_result = twilio_service.make_maintenance_reminder_call(
                machine_name=machine.name,
                maintenance_details="TEST: Routine maintenance reminder"
            )
            return jsonify({
                'success': True, 
                'message': 'Test maintenance call initiated',
                'call_result': call_result
            })

        elif call_type == 'sms':
            sms_results = twilio_service.send_emergency_sms_backup(
                machine_name=machine.name,
                incident_details="TEST: Critical system failure detected",
                incident_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            return jsonify({
                'success': True, 
                'message': 'Test SMS sent',
                'sms_results': sms_results
            })

        else:
            return jsonify({'error': 'Invalid call type. Use: emergency, maintenance, or sms'})

    except Exception as e:
        return jsonify({'error': str(e)})

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
def landing_page():
    """Landing page with navigation"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Main dashboard view"""
    machines = Machine.query.filter_by(is_active=True).all()
    recent_alerts = Alert.query.filter_by(is_acknowledged=False).order_by(Alert.created_at.desc()).limit(5).all()
    return render_template('dashboard.html', machines=machines, alerts=recent_alerts)

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

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
    """UPDATED: Set machine operation mode with flag reset"""
    global sent_maintenance_emails, sent_sabotage_emails, sent_twilio_calls

    data = request.get_json()
    mode = data.get('mode', 'normal')

    machine = Machine.query.get_or_404(machine_id)
    old_status = machine.status
    machine.status = mode
    machine.updated_at = datetime.utcnow()

    # RESET FLAGS WHEN STATUS CHANGES - PREVENTS PERMANENT BLOCKING
    if old_status != mode:
        sent_maintenance_emails.discard(machine_id)
        sent_sabotage_emails.discard(machine_id)
        sent_twilio_calls.discard(machine_id)
        print(f"🔄 Status changed: {machine.name} from {old_status} to {mode} - flags reset")

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

@app.route('/debug/machines')
def debug_machines():
    """Debug endpoint to check machine status"""
    machines = Machine.query.all()
    return jsonify({
        'total_machines': len(machines),
        'machines': [
            {
                'id': m.id,
                'name': m.name, 
                'type': m.machine_type,
                'status': m.status,
                'is_active': m.is_active
            } for m in machines
        ]
    })

@app.route('/debug/reset-email-flags')
def reset_email_flags():
    """NEW: Reset email flags to allow testing"""
    global sent_maintenance_emails, sent_sabotage_emails, sent_twilio_calls

    sent_maintenance_emails.clear()
    sent_sabotage_emails.clear()
    sent_twilio_calls.clear()

    return jsonify({
        'success': True,
        'message': 'Email and call flags reset - you can now test alerts again!'
    })

@app.route('/debug/test-email/<email_type>')
def test_email(email_type):
    """Test email functionality"""
    try:
        machine = Machine.query.first()
        if not machine:
            return jsonify({'error': 'No machines found'})

        if email_type == 'maintenance':
            test_readings = {
                'temperature': {'value': 450, 'unit': '°C', 'is_anomaly': True, 'anomaly_score': 0.6},
                'pressure': {'value': 35, 'unit': 'bar', 'is_anomaly': True, 'anomaly_score': 0.4}
            }
            enhanced_email_service.send_irregular_readings_alert(machine, test_readings, [])
            return jsonify({'success': True, 'message': 'Maintenance alert sent'})

        elif email_type == 'sabotage':
            incident_time = datetime.now().isoformat()
            critical_sensors = {
                'temperature': {'value': 730, 'unit': '°C', 'is_anomaly': True, 'anomaly_score': 0.95, 'normal_range': '250-400 °C'},
                'pressure': {'value': 48, 'unit': 'bar', 'is_anomaly': True, 'anomaly_score': 0.90, 'normal_range': '10-30 bar'}
            }
            pre_incident_data = [
                {'time_before_incident': 60, 'sensor_type': 'temperature', 'value': 380, 'unit': '°C', 'is_anomaly': False, 'trend': '→'},
                {'time_before_incident': 30, 'sensor_type': 'temperature', 'value': 420, 'unit': '°C', 'is_anomaly': True, 'trend': '📈'},
            ]
            enhanced_email_service.send_sabotage_incident_report(machine, incident_time, critical_sensors, pre_incident_data)
            return jsonify({'success': True, 'message': 'Sabotage incident report sent'})

        else:
            return jsonify({'error': 'Invalid email type. Use: maintenance or sabotage'})

    except Exception as e:
        return jsonify({'error': str(e)})

# Enhanced Data Generation with 4 Machines and Email Integration
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
    },
    "Heat Exchanger": {
        "sensors": {
            "inlet_temp": {"min": 25, "max": 150, "unit": "°C", "normal_range": [40, 90]},
            "outlet_temp": {"min": 30, "max": 180, "unit": "°C", "normal_range": [50, 120]},
            "pressure_drop": {"min": 0.1, "max": 3.0, "unit": "bar", "normal_range": [0.2, 1.5]},
            "flow_rate": {"min": 10, "max": 200, "unit": "L/min", "normal_range": [40, 160]}
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

def get_pre_incident_data(machine_id, incident_time, minutes_before=1):
    """Get sensor readings from specified minutes before incident"""
    try:
        incident_dt = datetime.fromisoformat(incident_time)
        start_time = incident_dt - timedelta(minutes=minutes_before)

        pre_incident_readings = SensorReading.query.filter(
            SensorReading.machine_id == machine_id,
            SensorReading.timestamp >= start_time,
            SensorReading.timestamp < incident_dt
        ).order_by(SensorReading.timestamp.desc()).limit(20).all()

        formatted_data = []
        for reading in pre_incident_readings:
            time_diff = int((incident_dt - reading.timestamp).total_seconds())
            formatted_data.append({
                'time_before_incident': time_diff,
                'sensor_type': reading.sensor_type,
                'value': reading.value,
                'unit': reading.unit,
                'is_anomaly': reading.is_anomaly,
                'trend': '📈' if reading.anomaly_score > 0.5 else '→'
            })

        return formatted_data

    except Exception as e:
        print(f"Error getting pre-incident data: {e}")
        return []

def detect_irregular_readings(current_readings):
    """Detect which sensors have irregular readings for maintenance alerts"""
    irregular_sensors = {}

    for sensor_type, reading in current_readings.items():
        if reading.get('anomaly_score', 0) > 0.3:
            irregular_sensors[sensor_type] = reading

    return irregular_sensors

def generate_machine_data(machine):
    """CORRECTED VERSION - Fixes email spam and adds Twilio integration"""
    global sent_maintenance_emails, sent_sabotage_emails, sent_twilio_calls

    machine_config = MACHINES_CONFIG.get(machine.machine_type)
    if not machine_config:
        return

    current_time = datetime.utcnow()
    critical_anomalies = []
    all_readings = {}

    for sensor_type, sensor_config in machine_config['sensors'].items():
        value = generate_sensor_value(sensor_type, sensor_config, machine.status)
        is_anomaly, anomaly_score = detect_simple_anomaly(value, sensor_config, machine.status)

        if is_anomaly and anomaly_score > 0.8:
            critical_anomalies.append((sensor_type, value, sensor_config['unit']))

        all_readings[sensor_type] = {
            'value': round(value, 2),
            'unit': sensor_config['unit'],
            'is_anomaly': is_anomaly,
            'anomaly_score': round(anomaly_score, 3),
            'normal_range': f"{sensor_config['normal_range'][0]} - {sensor_config['normal_range'][1]} {sensor_config['unit']}"
        }

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

        # 1. MAINTENANCE ALERT (with rate limiting to prevent spam)
        if machine.status == 'maintenance':
            irregular_sensors = detect_irregular_readings(all_readings)

            if irregular_sensors and machine.id not in sent_maintenance_emails:
                sent_maintenance_emails.add(machine.id)  # PREVENTS EMAIL SPAM
                print(f"📧 Sending maintenance alert for {machine.name}")

                recent_readings = SensorReading.query.filter(
                    SensorReading.machine_id == machine.id,
                    SensorReading.timestamp >= current_time - timedelta(minutes=5)
                ).all()

                enhanced_email_service.send_irregular_readings_alert(
                    machine=machine,
                    irregular_sensors=irregular_sensors,
                    reading_history=recent_readings
                )

                # MAKE MAINTENANCE CALL (with delay)
                if machine.id not in sent_twilio_calls:
                    sent_twilio_calls.add(machine.id)
                    def make_maintenance_call():
                        time.sleep(10)  # Wait 10 seconds after email
                        try:
                            twilio_service.make_maintenance_reminder_call(
                                machine_name=machine.name,
                                maintenance_details=f"{len(irregular_sensors)} sensors showing irregular readings"
                            )
                            print(f"📞 Maintenance call sent for {machine.name}")
                        except Exception as e:
                            print(f"❌ Failed to make maintenance call: {e}")

                    threading.Thread(target=make_maintenance_call, daemon=True).start()

        # 2. CRITICAL SABOTAGE ALERT (with rate limiting + Twilio integration)
        if critical_anomalies and machine.status == 'sabotage' and len(critical_anomalies) >= 2:

            if machine.id not in sent_sabotage_emails:  # PREVENTS EMAIL SPAM
                sent_sabotage_emails.add(machine.id)
                incident_time = current_time.isoformat()

                print(f"🚨 CRITICAL SABOTAGE DETECTED for {machine.name}")

                alert = Alert(
                    machine_id=machine.id,
                    alert_type='critical',
                    severity='critical',
                    title=f'🚨 SABOTAGE DETECTED: {machine.name}',
                    message=f'CRITICAL INCIDENT: Multiple sensor failures detected at {incident_time}',
                    sensor_data=json.dumps([{'sensor': s, 'value': v, 'unit': u} for s,v,u in critical_anomalies])
                )
                db.session.add(alert)
                db.session.commit()

                print(f"📧📞 Sending CRITICAL email + emergency calls for {machine.name}")

                # Get data for email and calls
                pre_incident_data = get_pre_incident_data(machine.id, incident_time, minutes_before=1)
                critical_sensors = {k: v for k, v in all_readings.items() if v.get('is_anomaly', False)}
                critical_details = f"Multiple critical sensor failures: {', '.join([f'{s}={v:.1f}{u}' for s,v,u in critical_anomalies])}"
                incident_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

                # Send email immediately
                enhanced_email_service.send_sabotage_incident_report(
                    machine=machine,
                    incident_time=incident_time,
                    critical_sensors=critical_sensors,
                    pre_incident_data=pre_incident_data
                )

                # MAKE EMERGENCY CALLS + SMS (THIS WAS MISSING!)
                if machine.id not in sent_twilio_calls:
                    sent_twilio_calls.add(machine.id)

                    def emergency_response():
                        try:
                            # Wait 15 seconds after email
                            time.sleep(15)

                            # Make emergency calls
                            print(f"📞 Making EMERGENCY CALLS for {machine.name}")
                            call_results = twilio_service.make_emergency_call(
                                machine_name=machine.name,
                                incident_details=critical_details,
                                incident_time=incident_time_str,
                                severity='CRITICAL'
                            )

                            print(f"✅ Emergency calls initiated: {len(call_results)} contacts")

                            # Send SMS backup after 45 seconds
                            time.sleep(45)
                            print(f"📱 Sending SMS backup for {machine.name}")
                            twilio_service.send_emergency_sms_backup(
                                machine_name=machine.name,
                                incident_details=critical_details,
                                incident_time=incident_time_str
                            )

                        except Exception as e:
                            print(f"❌ Error in emergency response: {e}")

                    # Run in background thread
                    threading.Thread(target=emergency_response, daemon=True).start()

                print(f"🚨 EMERGENCY PROTOCOL ACTIVATED - {machine.name}")

        # 3. RESET FLAGS WHEN STATUS CHANGES TO NORMAL (prevents permanent blocking)
        if machine.status == 'normal':
            sent_maintenance_emails.discard(machine.id)
            sent_sabotage_emails.discard(machine.id)
            sent_twilio_calls.discard(machine.id)

    except Exception as e:
        print(f"❌ Error in data generation: {e}")
        db.session.rollback()

def start_data_generation():
    """Main data generation loop"""
    print("🚀 Starting real-time sensor data generation for 4 machines...")
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

        except Exception as e:
            print(f"❌ Error in data generation: {e}")

        time.sleep(3)

def create_tables():
    """Create database tables and sample data"""
    print("🔧 Creating database tables...")

    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully!")

        existing_count = Machine.query.count()

        if existing_count != 4:
            Machine.query.delete()

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
                },
                {
                    'name': 'Heat Exchanger HX-005',
                    'machine_type': 'Heat Exchanger',
                    'description': 'Shell-and-tube heat exchanger for thermal processing',
                    'location': 'Building C - Floor 1'
                }
            ]

            for machine_data in machines_data:
                machine = Machine(**machine_data)
                db.session.add(machine)

            db.session.commit()
            print("✅ Added exactly 4 machines to database")

if __name__ == '__main__':
    create_tables()

    data_thread = threading.Thread(target=start_data_generation, daemon=True)
    data_thread.start()

    print("🚀 Starting Complete Industrial Predictive Maintenance System...")
    print("🏠 Landing page: http://localhost:5000")
    print("📊 Dashboard: http://localhost:5000/dashboard")
    print("📧 Test maintenance email: http://localhost:5000/debug/test-email/maintenance")
    print("🚨 Test sabotage email: http://localhost:5000/debug/test-email/sabotage")
    print("📞 Test emergency call: http://localhost:5000/debug/test-call/emergency")
    print("📞 Test maintenance call: http://localhost:5000/debug/test-call/maintenance")
    print("📱 Test SMS: http://localhost:5000/debug/test-call/sms")
    print("🔧 Debug machines: http://localhost:5000/debug/machines")
    print("🔄 Reset flags: http://localhost:5000/debug/reset-email-flags")
    app.run(debug=True, threaded=True, port=5000)
