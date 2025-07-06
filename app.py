import os
import sys
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
import pandas as pd
from io import BytesIO
import sqlite3
import tempfile
from functools import wraps
from db import db

# Set environment for production
os.environ.setdefault('FLASK_ENV', 'production')

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "ancoracas25_default_secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure database
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
import time

# ✅ Neon PostgreSQL Database URL
DATABASE_URL = "postgresql://ccvdb_owner:npg_LF0VykApeB1N@ep-weathered-bird-a9lthhlj-pooler.gwc.azure.neon.tech/ccvdb?sslmode=require"

def test_database_connection(retries=3):
    """Test database connection with retry logic"""
    for attempt in range(retries):
        try:
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(text('SELECT 1'))
                print("✅ Connessione a Neon PostgreSQL riuscita")
                return True
        except OperationalError as e:
            print(f"❌ Tentativo {attempt + 1} fallito: {str(e)}")
            if attempt < retries - 1:
                time.sleep(2)  # Wait 2 seconds before retry
            else:
                print("❌ Connessione a Neon PostgreSQL fallita dopo tutti i tentativi.")
                return False
    return False

# Test connection on startup (only in development)
if os.environ.get('FLASK_ENV') == 'development':
    if not test_database_connection():
        print("❌ Impossibile connettersi al database. Arresto dell'app.")
        sys.exit(1)
else:
    # In production, try connection but don't exit if it fails initially
    try:
        test_database_connection()
    except Exception as e:
        print(f"⚠️ Warning: Database connection issue on startup: {e}")
        print("🔄 Will retry connections as needed...")

# Configurazione Flask-SQLAlchemy with more robust settings
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 3600,  # Recycle connections every hour
    "pool_pre_ping": True,  # Test connections before use
    "pool_timeout": 20,     # Timeout after 20 seconds
    "max_overflow": 0,      # Don't allow overflow connections
    "pool_size": 5,         # Keep 5 connections in pool
}

# Initialize database with app
db.init_app(app)

# Add context processor for datetime
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Import models (after db is defined)
from models import Guest, CustomField, Setting, Appointment

# Create database tables
with app.app_context():
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Test connection first
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            
            # Create tables
            db.create_all()

            # Add default password setting if not exists
            if not Setting.query.filter_by(key='password').first():
                default_password = Setting(key='password', value='ancoracas25')
                db.session.add(default_password)
                db.session.commit()

            print("✅ Database inizializzato con successo")
            break
            
        except Exception as e:
            retry_count += 1
            print(f"❌ Tentativo {retry_count} - Errore durante l'inizializzazione del database: {str(e)}")
            
            if retry_count < max_retries:
                import time
                time.sleep(2)  # Wait 2 seconds before retry
            else:
                print("⚠️ Continuando senza inizializzazione completa del database...")
                break

# Import utility functions
from utils import check_expiring_permits, is_tomorrow
from fiscal_code import calculate_fiscal_code

# Import forms
from forms import GuestForm, SettingsForm

def handle_database_error(func):
    """Decorator to handle database errors gracefully"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OperationalError as e:
            app.logger.error(f"Database error in {func.__name__}: {str(e)}")
            db.session.rollback()
            flash('Errore di connessione al database. Riprova tra qualche minuto.', 'danger')
            return redirect(url_for('dashboard'))
        except Exception as e:
            app.logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            db.session.rollback()
            flash('Si è verificato un errore imprevisto.', 'danger')
            return redirect(url_for('dashboard'))
    return wrapper

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Accesso richiesto', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        
        # Get stored password from settings or use default
        with app.app_context():
            setting = Setting.query.filter_by(key='password').first()
            stored_password = setting.value if setting else 'ancoracas25'
        
        if password == stored_password:
            session['logged_in'] = True
            flash('Accesso effettuato con successo', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Password non corretta', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Disconnessione effettuata', 'success')
    return redirect(url_for('login'))

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
@handle_database_error
def dashboard():
    # Get count of guests
    total_guests = Guest.query.count()
    
    # Get count of expiring permits (within 7 days)
    expiring_permits = check_expiring_permits()
    
    # Get latest added guests
    latest_guests = Guest.query.order_by(Guest.entry_date.desc()).limit(5).all()
    
    # Get upcoming appointments (next 7 days)
    today = datetime.now().date()
    week_from_now = today + timedelta(days=7)
    upcoming_appointments = Appointment.query.filter(
        Appointment.appointment_date >= today,
        Appointment.appointment_date <= week_from_now,
        Appointment.is_completed == False
    ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()
    
    return render_template('dashboard.html', 
                          total_guests=total_guests, 
                          expiring_permits=len(expiring_permits),
                          latest_guests=latest_guests,
                          expiring_list=expiring_permits,
                          upcoming_appointments=upcoming_appointments,
                          today=today,
                          is_tomorrow=is_tomorrow)

@app.route('/new_guest', methods=['GET', 'POST'])
@login_required
def new_guest():
    form = GuestForm()
    
    # Get all existing guests for family relations selector
    all_guests = Guest.query.all()
    
    if request.method == 'POST':
        try:
            # Helper function to parse dates in different formats
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    # First try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    try:
                        # Then try DD/MM/YYYY format
                        return datetime.strptime(date_str, '%d/%m/%Y')
                    except ValueError:
                        # If that fails too, raise an exception with clear message
                        raise ValueError(f"Formato data non valido: {date_str}. Usa DD/MM/YYYY o YYYY-MM-DD.")
            
            # Parse dates from the form
            birth_date = parse_date(request.form['birth_date'])
            permit_date = parse_date(request.form['permit_date'])
            permit_expiry = permit_date + timedelta(days=180) if permit_date else None
            health_card_expiry = parse_date(request.form['health_card_expiry'])
            entry_date = parse_date(request.form['entry_date']) if request.form['entry_date'] else datetime.now()
            check_in_date = parse_date(request.form.get('check_in_date')) if request.form.get('check_in_date') else None
            check_out_date = parse_date(request.form.get('check_out_date')) if request.form.get('check_out_date') else None
            
            # Create new guest from form data
            new_guest = Guest(
                last_name=request.form['last_name'],
                first_name=request.form['first_name'],
                gender=request.form['gender'],
                birth_place=request.form['birth_place'],
                province=request.form['province'],
                birth_date=birth_date,
                permit_number=request.form['permit_number'],
                permit_date=permit_date,
                permit_expiry=permit_expiry,
                health_card=request.form['health_card'],
                health_card_expiry=health_card_expiry,
                entry_date=entry_date,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                room_number=request.form['room_number'],
                floor=request.form['floor'],
                family_relations=request.form['family_relations'],
                fiscal_code=request.form['fiscal_code'],
                country_code=request.form['country_code']
            )
            
            # Save to database
            db.session.add(new_guest)
            db.session.commit()
            
            # Handle custom fields
            for key, value in request.form.items():
                if key.startswith('custom_field_'):
                    field_name = request.form.get(f'custom_field_name_{key.split("_")[-1]}')
                    if field_name and value:
                        custom_field = CustomField(
                            guest_id=new_guest.id,
                            field_name=field_name,
                            field_value=value
                        )
                        db.session.add(custom_field)
            
            db.session.commit()
            flash('Ospite aggiunto con successo', 'success')
            return redirect(url_for('archive'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante il salvataggio: {str(e)}', 'danger')
    
    return render_template('new_guest.html', form=form, all_guests=all_guests)

@app.route('/archive')
@login_required
@handle_database_error
def archive():
    try:
        guests = Guest.query.all()
        # calcola la data di oggi (solo data, senza orario)
        now = datetime.now().date()
        
        # Pre-validate and clean all guest data to catch any issues before rendering
        validated_guests = []
        for guest in guests:
            try:
                # Validate and convert birth_date
                if guest.birth_date:
                    if isinstance(guest.birth_date, datetime):
                        guest.birth_date = guest.birth_date.date()
                    elif isinstance(guest.birth_date, str):
                        # Try to parse string dates
                        try:
                            guest.birth_date = datetime.strptime(guest.birth_date, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                guest.birth_date = datetime.strptime(guest.birth_date, '%d/%m/%Y').date()
                            except ValueError:
                                guest.birth_date = None
                
                # Validate other date fields
                for date_field in ['permit_expiry', 'entry_date', 'permit_date', 'health_card_expiry', 'check_in_date', 'check_out_date']:
                    date_value = getattr(guest, date_field, None)
                    if date_value and isinstance(date_value, datetime):
                        setattr(guest, date_field, date_value.date())
                
                # Ensure string fields are not None
                for str_field in ['room_number', 'birth_place', 'last_name', 'first_name']:
                    if getattr(guest, str_field, None) is None:
                        setattr(guest, str_field, '')
                
                validated_guests.append(guest)
                
            except Exception as guest_error:
                app.logger.error(f"Error validating guest {guest.id}: {str(guest_error)}")
                # Continue with other guests even if one fails
                continue
            
        return render_template('archive.html', guests=validated_guests, now=now)
    except Exception as e:
        import traceback
        app.logger.error(f"Errore nella route archive: {str(e)}")
        app.logger.error(traceback.format_exc())
        flash('Errore durante il caricamento della lista ospiti. Controlla i log per maggiori dettagli.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/guest/<int:guest_id>')
@login_required
def guest_detail(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    custom_fields = CustomField.query.filter_by(guest_id=guest_id).all()
    return render_template('guest_detail.html', guest=guest, custom_fields=custom_fields)

@app.route('/guest/<int:guest_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_guest(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    custom_fields = CustomField.query.filter_by(guest_id=guest_id).all()
    
    # Get all existing guests for family relations selector
    all_guests = Guest.query.all()
    
    if request.method == 'POST':
        try:
            # Helper function to parse dates in different formats
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    # First try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    try:
                        # Then try DD/MM/YYYY format
                        return datetime.strptime(date_str, '%d/%m/%Y')
                    except ValueError:
                        # If that fails too, raise an exception with clear message
                        raise ValueError(f"Formato data non valido: {date_str}. Usa DD/MM/YYYY o YYYY-MM-DD.")
            
            # Update guest data
            guest.last_name = request.form['last_name']
            guest.first_name = request.form['first_name']
            guest.gender = request.form['gender']
            guest.birth_place = request.form['birth_place']
            guest.province = request.form['province']
            guest.birth_date = parse_date(request.form['birth_date'])
            guest.permit_number = request.form['permit_number']
            
            if request.form['permit_date']:
                guest.permit_date = parse_date(request.form['permit_date'])
                guest.permit_expiry = guest.permit_date + timedelta(days=180)
            
            guest.health_card = request.form['health_card']
            
            if request.form['health_card_expiry']:
                guest.health_card_expiry = parse_date(request.form['health_card_expiry'])
            
            if request.form['entry_date']:
                guest.entry_date = parse_date(request.form['entry_date'])
            
            if request.form.get('check_in_date'):
                guest.check_in_date = parse_date(request.form['check_in_date'])
                
            if request.form.get('check_out_date'):
                guest.check_out_date = parse_date(request.form['check_out_date'])
                
            guest.room_number = request.form['room_number']
            guest.floor = request.form['floor']
            guest.family_relations = request.form['family_relations']
            guest.fiscal_code = request.form['fiscal_code']
            guest.country_code = request.form['country_code']
            
            # Handle custom fields
            # First, delete existing custom fields
            CustomField.query.filter_by(guest_id=guest_id).delete()
            
            # Then add new custom fields
            for key, value in request.form.items():
                if key.startswith('custom_field_'):
                    field_name = request.form.get(f'custom_field_name_{key.split("_")[-1]}')
                    if field_name and value:
                        custom_field = CustomField(
                            guest_id=guest.id,
                            field_name=field_name,
                            field_value=value
                        )
                        db.session.add(custom_field)
            
            db.session.commit()
            flash('Ospite aggiornato con successo', 'success')
            return redirect(url_for('guest_detail', guest_id=guest_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante l\'aggiornamento: {str(e)}', 'danger')
    
    return render_template('new_guest.html', guest=guest, custom_fields=custom_fields, edit_mode=True, all_guests=all_guests)

@app.route('/guest/<int:guest_id>/delete', methods=['POST'])
@login_required
def delete_guest(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    
    try:
        # Delete custom fields first
        CustomField.query.filter_by(guest_id=guest_id).delete()
        
        # Delete guest
        db.session.delete(guest)
        db.session.commit()
        flash('Ospite eliminato con successo', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Errore durante l\'eliminazione: {str(e)}', 'danger')
    
    return redirect(url_for('archive'))

@app.route('/import_data', methods=['POST'])
@login_required
def import_data():
    if 'import_file' not in request.files:
        flash('Nessun file selezionato', 'danger')
        return redirect(url_for('export_data'))
    
    file = request.files['import_file']
    if file.filename == '':
        flash('Nessun file selezionato', 'danger')
        return redirect(url_for('export_data'))
    
    # Verifica se la checkbox di conferma è spuntata
    if 'confirm_import' not in request.form:
        flash('È necessario confermare l\'importazione', 'danger')
        return redirect(url_for('export_data'))
    
    try:
        # Controlla l'estensione del file
        if file.filename.endswith('.xlsx'):
            # Importa da Excel
            df = pd.read_excel(file)
        elif file.filename.endswith('.csv'):
            # Importa da CSV
            df = pd.read_csv(file)
        else:
            flash('Formato file non supportato. Usa Excel (.xlsx) o CSV (.csv)', 'danger')
            return redirect(url_for('export_data'))
        
        # Normalizza i nomi delle colonne (case insensitive e gestisce spazi/underscore)
        column_mapping = {
            'last_name': ['last_name', 'lastname', 'cognome', 'surname'],
            'first_name': ['first_name', 'firstname', 'nome', 'name'],
            'gender': ['gender', 'sesso', 'genere', 'sex'],
            'birth_date': ['birth_date', 'birthdate', 'data di nascita', 'data nascita', 'nascita']
        }
        
        # Converti tutti i nomi delle colonne in minuscolo per il confronto
        df.columns = [col.lower().strip() for col in df.columns]
        
        # Mappa le colonne alla struttura interna
        mapped_df = pd.DataFrame()
        missing_columns = []
        
        for internal_col, possible_names in column_mapping.items():
            found = False
            for possible_name in possible_names:
                if possible_name.lower() in df.columns:
                    mapped_df[internal_col] = df[possible_name.lower()]
                    found = True
                    break
            if not found:
                missing_columns.append(internal_col)
        
        if missing_columns:
            flash(f'File non valido. Impossibile identificare le colonne: {", ".join(missing_columns)}', 'danger')
            flash(f'Per favore, assicurati che il file contenga le seguenti informazioni: Cognome, Nome, Sesso, Data di nascita', 'info')
            return redirect(url_for('export_data'))
            
        # Sostituzione del dataframe originale con quello mappato
        df = mapped_df
        
        # Inizia una transazione per assicurarsi che tutte le operazioni vadano a buon fine
        db.session.begin_nested()
        
        # Opzionale: svuota la tabella degli ospiti esistenti
        # Guest.query.delete()
        
        # Importa ogni riga nel database
        guests_imported = 0
        for _, row in df.iterrows():
            try:
                # Funzione helper per convertire le date in modo sicuro
                def safe_date_convert(date_value):
                    if pd.isna(date_value) or date_value == '' or date_value is None:
                        return None
                    try:
                        # Prova diversi formati di data
                        try:
                            # Formato standard
                            return pd.to_datetime(date_value).date()
                        except:
                            # Prova il formato italiano (gg/mm/aaaa)
                            return pd.to_datetime(date_value, format='%d/%m/%Y').date()
                    except Exception as date_err:
                        app.logger.error(f"Errore nella conversione della data '{date_value}': {str(date_err)}")
                        return None
                
                # Crea un nuovo ospite con i dati dal file
                guest = Guest(
                    last_name=str(row.get('last_name', '')),
                    first_name=str(row.get('first_name', '')),
                    gender=str(row.get('gender', '')),
                    birth_place=str(row.get('birth_place', '')),
                    province=str(row.get('province', '')),
                    birth_date=safe_date_convert(row.get('birth_date')),
                    fiscal_code=str(row.get('fiscal_code', '')),
                    country_code=str(row.get('country_code', '')),
                    permit_number=str(row.get('permit_number', '')),
                    permit_date=safe_date_convert(row.get('permit_date')),
                    permit_expiry=safe_date_convert(row.get('permit_expiry')),
                    health_card=str(row.get('health_card', '')),
                    health_card_expiry=safe_date_convert(row.get('health_card_expiry')),
                    entry_date=safe_date_convert(row.get('entry_date')),
                    exit_date=safe_date_convert(row.get('exit_date')),
                    check_in_date=safe_date_convert(row.get('check_in_date')),
                    check_out_date=safe_date_convert(row.get('check_out_date')),
                    room_number=str(row.get('room_number', '')),
                    floor=str(row.get('floor', '')),
                    family_relations=str(row.get('family_relations', ''))
                )
                
                db.session.add(guest)
                guests_imported += 1
                
                # Commit ogni 100 record per evitare problemi di memoria
                if guests_imported % 100 == 0:
                    db.session.commit()
                
            except Exception as e:
                app.logger.error(f"Errore importando riga {_}: {str(e)}")
                # Continua con la prossima riga se c'è un errore
                continue
        
        # Commit finale
        db.session.commit()
        flash(f'Importazione completata con successo! {guests_imported} ospiti importati.', 'success')
        
    except Exception as e:
        # In caso di errore, annulla tutte le modifiche
        db.session.rollback()
        app.logger.error(f"Errore durante l'importazione: {str(e)}")
        flash(f'Errore durante l\'importazione: {str(e)}', 'danger')
    
    return redirect(url_for('export_data'))

@app.route('/export_data', methods=['GET', 'POST'])
@login_required
def export_data():
    if request.method == 'POST':
        # Get filter parameters
        nationality = request.form.get('nationality')
        age_filter = request.form.get('age_filter')
        room = request.form.get('room')
        entry_date_from = request.form.get('entry_date_from')
        entry_date_to = request.form.get('entry_date_to')
        
        # Build query with filters
        query = Guest.query
        
        if nationality:
            query = query.filter(Guest.birth_place == nationality)
        
        if age_filter:
            today = datetime.now()
            adult_date = today - timedelta(days=365.25 * 18)  # 18 years ago
            
            if age_filter == 'adult':
                query = query.filter(Guest.birth_date <= adult_date)
            elif age_filter == 'minor':
                query = query.filter(Guest.birth_date > adult_date)
        
        if room:
            query = query.filter(Guest.room_number == room)
        
        if entry_date_from:
            try:
                # Prima prova il formato italiano
                date_from = datetime.strptime(entry_date_from, '%d/%m/%Y')
            except ValueError:
                # Se non funziona, prova il formato standard
                date_from = datetime.strptime(entry_date_from, '%Y-%m-%d')
            query = query.filter(Guest.entry_date >= date_from)
        
        if entry_date_to:
            try:
                # Prima prova il formato italiano
                date_to = datetime.strptime(entry_date_to, '%d/%m/%Y')
            except ValueError:
                # Se non funziona, prova il formato standard
                date_to = datetime.strptime(entry_date_to, '%Y-%m-%d')
            query = query.filter(Guest.entry_date <= date_to)
        
        # Execute query
        guests = query.all()
        
        # Prepare data for export
        data = []
        for guest in guests:
            row = {
                'ID': guest.id,
                'Cognome': guest.last_name,
                'Nome': guest.first_name,
                'Sesso': guest.gender,
                'Luogo di nascita': guest.birth_place,
                'Provincia': guest.province,
                'Data di nascita': guest.birth_date.strftime('%d/%m/%Y') if guest.birth_date else '',
                'Codice Fiscale': guest.fiscal_code,
                'Permesso di soggiorno': guest.permit_number,
                'Data rilascio': guest.permit_date.strftime('%d/%m/%Y') if guest.permit_date else '',
                'Scadenza': guest.permit_expiry.strftime('%d/%m/%Y') if guest.permit_expiry else '',
                'Tessera sanitaria': guest.health_card,
                'Scadenza tessera': guest.health_card_expiry.strftime('%d/%m/%Y') if guest.health_card_expiry else '',
                'Data ingresso': guest.entry_date.strftime('%d/%m/%Y') if guest.entry_date else '',
                'Stanza': guest.room_number,
                'Piano': guest.floor,
                'Relazioni familiari': guest.family_relations
            }
            
            # Add custom fields
            custom_fields = CustomField.query.filter_by(guest_id=guest.id).all()
            for cf in custom_fields:
                row[cf.field_name] = cf.field_value
                
            data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Current date for the export
        current_date = datetime.now().strftime('%d/%m/%Y')
        
        # Choose export format
        export_format = request.form.get('export_format', 'excel')
        
        if export_format == 'excel':
            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Ospiti', index=False)
                workbook = writer.book
                worksheet = writer.sheets['Ospiti']
                
                # Add footer with current date
                worksheet.set_footer(f'File aggiornato al {current_date}')
                
                # Format header
                header_format = workbook.add_format({
                    'bold': True,
                    'border': 1,
                    'bg_color': '#D9E1F2',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Apply header format
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    worksheet.set_column(col_num, col_num, 15)
            
            output.seek(0)
            return send_file(
                output,
                as_attachment=True,
                download_name=f'Ancora_CAS_Export_{datetime.now().strftime("%d%m%Y")}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
        elif export_format == 'pdf':
            # Generate PDF using a temporary HTML file
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Ancora CAS - Export</title>
                    <style>
                        body { font-family: Arial, sans-serif; }
                        table { width: 100%; border-collapse: collapse; }
                        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                        th { background-color: #f2f2f2; }
                        .footer { margin-top: 20px; font-style: italic; }
                    </style>
                </head>
                <body>
                    <h1>Ancora CAS - Elenco Ospiti</h1>
                    {df.to_html(index=False)}
                    <div class="footer">File aggiornato al {current_date}</div>
                </body>
                </html>
                """
                f.write(html_content.encode('utf-8'))
                temp_filename = f.name
            
            try:
                # Create PDF from HTML (we'll use a simple approach with the weasyprint package)
                # Note: In a real implementation, you would need to install weasyprint
                from weasyprint import HTML
                pdf_bytes = HTML(temp_filename).write_pdf()
                
                # Create BytesIO object and write PDF content to it
                output = BytesIO()
                output.write(pdf_bytes)
                output.seek(0)
                
                # Remove temporary HTML file
                os.unlink(temp_filename)
                
                return send_file(
                    output,
                    as_attachment=True,
                    download_name=f'Ancora_CAS_Export_{datetime.now().strftime("%Y%m%d")}.pdf',
                    mimetype='application/pdf'
                )
            except Exception as e:
                flash(f'Errore durante la generazione del PDF: {str(e)}', 'danger')
                return redirect(url_for('export_data'))
    
    # Get unique values for filters
    nationalities = db.session.query(Guest.birth_place).distinct().all()
    rooms = db.session.query(Guest.room_number).distinct().all()
    
    return render_template('export.html', 
                          nationalities=[n[0] for n in nationalities if n[0]],
                          rooms=[r[0] for r in rooms if r[0]])

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = SettingsForm()
    
    if request.method == 'POST':
        try:
            # Update password if provided
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if new_password:
                if new_password != confirm_password:
                    flash('Le password non corrispondono', 'danger')
                    return redirect(url_for('settings'))
                
                # Update password in settings
                password_setting = Setting.query.filter_by(key='password').first()
                if not password_setting:
                    password_setting = Setting(key='password', value='ancoracas25')
                    db.session.add(password_setting)
                
                password_setting.value = new_password
                db.session.commit()
                flash('Password aggiornata con successo', 'success')
                
            return redirect(url_for('settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante il salvataggio delle impostazioni: {str(e)}', 'danger')
    
    return render_template('settings.html', form=form)

@app.route('/calculate_fiscal_code', methods=['POST'])
def calc_fiscal_code():
    data = request.get_json()
    
    last_name = data.get('last_name', '')
    first_name = data.get('first_name', '')
    gender = data.get('gender', '')
    birth_date = data.get('birth_date', '')
    birth_place = data.get('birth_place', '')
    
    if not all([last_name, first_name, gender, birth_date, birth_place]):
        return jsonify({'error': 'Dati mancanti per il calcolo del codice fiscale'})
    
    try:
        # Prova a interpretare la data in diversi formati
        try:
            birth_date = datetime.strptime(birth_date, '%Y-%m-%d')  # Formato standard
        except ValueError:
            try:
                birth_date = datetime.strptime(birth_date, '%d/%m/%Y')  # Formato italiano
            except ValueError:
                return jsonify({'error': 'Formato data non riconosciuto. Utilizzare DD/MM/YYYY o YYYY-MM-DD'})
                
        fiscal_code = calculate_fiscal_code(last_name, first_name, gender, birth_date, birth_place)
        return jsonify({'fiscal_code': fiscal_code})
    except Exception as e:
        app.logger.error(f"Errore calcolo codice fiscale: {str(e)}")
        return jsonify({'error': str(e)})

@app.context_processor
def utility_processor():
    def calculate_age(birth_date):
        if not birth_date:
            return None
        try:
            # Ensure we're working with date objects
            if isinstance(birth_date, datetime):
                birth_date = birth_date.date()
            elif isinstance(birth_date, str):
                # If it's a string, try to parse it
                try:
                    birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        birth_date = datetime.strptime(birth_date, '%d/%m/%Y').date()
                    except ValueError:
                        return None
            
            if not hasattr(birth_date, 'year'):
                return None
                
            today = datetime.now().date()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            return age if age >= 0 else None
        except Exception as e:
            # Log the error but don't crash the page
            app.logger.error(f"Error calculating age for birth_date {birth_date}: {str(e)}")
            return None
    
    def safe_date_format(date_obj, format_str='%d/%m/%Y'):
        if not date_obj:
            return '-'
        try:
            if isinstance(date_obj, datetime):
                return date_obj.strftime(format_str)
            elif hasattr(date_obj, 'strftime'):
                return date_obj.strftime(format_str)
            else:
                return str(date_obj)
        except Exception:
            return '-'
    
    return dict(calculate_age=calculate_age, safe_date_format=safe_date_format)

# Questa sezione è già stata gestita in precedenza ed è duplicata
# La manteniamo come parte del codice ma è già gestita sopra

# Routes for appointment management
@app.route('/appointments')
@login_required
def appointments():
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', 'all')
    
    # Base query
    query = Appointment.query
    
    # Apply date filters
    if date_from:
        try:
            # Helper function to parse dates in different formats
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    # First try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        # Then try DD/MM/YYYY format
                        return datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        # If that fails too, raise an exception with clear message
                        raise ValueError(f"Formato data non valido: {date_str}. Usa DD/MM/YYYY o YYYY-MM-DD.")
            
            date_from_obj = parse_date(date_from)
            query = query.filter(Appointment.appointment_date >= date_from_obj)
        except ValueError:
            flash(f'Formato data inizio non valido: {date_from}', 'danger')
    
    if date_to:
        try:
            date_to_obj = parse_date(date_to)
            query = query.filter(Appointment.appointment_date <= date_to_obj)
        except ValueError:
            flash(f'Formato data fine non valido: {date_to}', 'danger')
    
    # Apply status filter
    if status == 'pending':
        query = query.filter(Appointment.is_completed == False)
    elif status == 'completed':
        query = query.filter(Appointment.is_completed == True)
    
    # Order by date and time
    appointments = query.order_by(Appointment.appointment_date, Appointment.appointment_time).all()
    
    # Prepare statistics
    stats = {
        'total': Appointment.query.count(),
        'pending': Appointment.query.filter(Appointment.is_completed == False).count(),
        'completed': Appointment.query.filter(Appointment.is_completed == True).count()
    }
    
    # Get today and tomorrow dates for highlighting
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    return render_template(
        'appointments.html', 
        appointments=appointments, 
        stats=stats,
        today=today,
        tomorrow=tomorrow
    )

@app.route('/new_appointment', methods=['GET', 'POST'])
@login_required
def new_appointment():
    # Get all guests for the dropdown
    all_guests = Guest.query.order_by(Guest.last_name).all()
    
    if request.method == 'POST':
        try:
            # Helper function to parse dates in different formats
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    # First try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        # Then try DD/MM/YYYY format
                        return datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        # If that fails too, raise an exception with clear message
                        raise ValueError(f"Formato data non valido: {date_str}. Usa DD/MM/YYYY o YYYY-MM-DD.")
            
            # Create new appointment from form data
            guest_id = request.form['guest_id']
            title = request.form['title']
            appointment_date = parse_date(request.form['appointment_date'])
            appointment_time = datetime.strptime(request.form['appointment_time'], '%H:%M').time()
            
            # Optional fields
            location = request.form.get('location', '')
            description = request.form.get('description', '')
            is_completed = 'is_completed' in request.form
            
            # Create appointment
            appointment = Appointment(
                guest_id=guest_id,
                title=title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                location=location,
                description=description,
                is_completed=is_completed
            )
            
            # Save to database
            db.session.add(appointment)
            db.session.commit()
            
            flash('Appuntamento aggiunto con successo', 'success')
            return redirect(url_for('calendar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante il salvataggio: {str(e)}', 'danger')
    
    return render_template('new_appointment.html', all_guests=all_guests)

@app.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html')

@app.route('/get_appointments')
@login_required
def get_appointments():
    # Get all appointments
    appointments = Appointment.query.all()
    
    # Format for FullCalendar
    events = []
    for appointment in appointments:
        # Get guest name
        guest = Guest.query.get(appointment.guest_id)
        guest_name = f"{guest.first_name} {guest.last_name}" if guest else "Ospite sconosciuto"
        
        # Create event
        event = {
            'id': appointment.id,
            'title': f"{appointment.title} - {guest_name}",
            'start': f"{appointment.appointment_date.isoformat()}T{appointment.appointment_time.isoformat()}",
            'classNames': []
        }
        
        # Add styling for today's and tomorrow's appointments
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        if appointment.appointment_date == today:
            event['classNames'].append('fc-event-today')
        elif appointment.appointment_date == tomorrow:
            event['classNames'].append('fc-event-tomorrow')
            
        if appointment.is_completed:
            event['classNames'].append('fc-event-completed')
            
        events.append(event)
    
    return jsonify(events)

@app.route('/appointment/<int:appointment_id>')
@login_required
def appointment_detail(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    return render_template('appointment_detail.html', appointment=appointment)

@app.route('/appointment/<int:appointment_id>/json')
@login_required
def appointment_json(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    guest = Guest.query.get(appointment.guest_id)
    
    return jsonify({
        'id': appointment.id,
        'guest_id': appointment.guest_id,
        'guest_name': f"{guest.first_name} {guest.last_name}" if guest else "Ospite sconosciuto",
        'title': appointment.title,
        'date': appointment.appointment_date.strftime('%d/%m/%Y'),
        'time': appointment.appointment_time.strftime('%H:%M'),
        'location': appointment.location,
        'description': appointment.description,
        'is_completed': appointment.is_completed
    })

@app.route('/appointment/<int:appointment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    all_guests = Guest.query.order_by(Guest.last_name).all()
    
    if request.method == 'POST':
        try:
            # Helper function to parse dates in different formats
            def parse_date(date_str):
                if not date_str:
                    return None
                try:
                    # First try YYYY-MM-DD format
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        # Then try DD/MM/YYYY format
                        return datetime.strptime(date_str, '%d/%m/%Y').date()
                    except ValueError:
                        # If that fails too, raise an exception with clear message
                        raise ValueError(f"Formato data non valido: {date_str}. Usa DD/MM/YYYY o YYYY-MM-DD.")
            
            # Update appointment from form data
            appointment.guest_id = request.form['guest_id']
            appointment.title = request.form['title']
            appointment.appointment_date = parse_date(request.form['appointment_date'])
            appointment.appointment_time = datetime.strptime(request.form['appointment_time'], '%H:%M').time()
            appointment.location = request.form.get('location', '')
            appointment.description = request.form.get('description', '')
            appointment.is_completed = 'is_completed' in request.form
            
            # Save to database
            db.session.commit()
            
            flash('Appuntamento aggiornato con successo', 'success')
            return redirect(url_for('appointment_detail', appointment_id=appointment_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante l\'aggiornamento: {str(e)}', 'danger')
    
    return render_template('new_appointment.html', appointment=appointment, edit_mode=True, all_guests=all_guests)

@app.route('/appointment/<int:appointment_id>/delete', methods=['POST'])
@login_required
def delete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    try:
        db.session.delete(appointment)
        db.session.commit()
        flash('Appuntamento eliminato con successo', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Errore durante l\'eliminazione: {str(e)}', 'danger')
    
    return redirect(url_for('calendar'))

@app.route('/appointment/<int:appointment_id>/complete', methods=['POST'])
@login_required
def complete_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    try:
        appointment.is_completed = True
        db.session.commit()
        flash('Appuntamento segnato come completato', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Errore durante l\'aggiornamento: {str(e)}', 'danger')
    
    return redirect(url_for('appointment_detail', appointment_id=appointment_id))

if __name__ == '__main__':
    # Production-ready configuration
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV', 'production') == 'development'
    
    app.run(
        host='0.0.0.0', 
        port=port, 
        debug=debug_mode,
        threaded=True  # Handle multiple requests concurrently
    )
