from datetime import datetime
from db import db  # ✅ FIXED: Import db from db.py to avoid circular import

class Guest(db.Model):
    __tablename__ = 'guests'
    
    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(1), nullable=False)  # M or F
    birth_place = db.Column(db.String(100), nullable=False)
    province = db.Column(db.String(2))  # Province code (2 chars)
    birth_date = db.Column(db.Date, nullable=False)
    fiscal_code = db.Column(db.String(16))
    country_code = db.Column(db.String(4))  # Foreign country code (Z + 3 digits)
    permit_number = db.Column(db.String(50))
    permit_date = db.Column(db.Date)
    permit_expiry = db.Column(db.Date)
    health_card = db.Column(db.String(50))
    health_card_expiry = db.Column(db.Date)
    entry_date = db.Column(db.Date, default=datetime.utcnow)
    exit_date = db.Column(db.Date)
    check_in_date = db.Column(db.Date)  # Data check in
    check_out_date = db.Column(db.Date)  # Data check out
    room_number = db.Column(db.String(10))
    floor = db.Column(db.String(10))
    family_relations = db.Column(db.Text)
    
    # Relationship with custom fields
    custom_fields = db.relationship('CustomField', backref='guest', lazy=True, cascade="all, delete-orphan")
    
    # Relationship with appointments
    appointments = db.relationship('Appointment', backref='guest', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Guest {self.first_name} {self.last_name}>'

class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    field_value = db.Column(db.Text)
    
    def __repr__(self):
        return f'<CustomField {self.field_name}>'

class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(100))
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Appointment {self.title} for {self.guest.first_name} {self.guest.last_name}>'

class Setting(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Setting {self.key}>'
