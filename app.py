import streamlit as st
import sqlite3
import bcrypt
import pandas as pd
from datetime import datetime, timedelta
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Google Calendar imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    st.warning("Google Calendar libraries not installed. Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

# Configuration for deployment
def get_config():
    """Get configuration from Streamlit secrets or environment variables"""
    config = {}
    
    try:
        # Try Streamlit secrets first (for Streamlit Cloud)
        config['google_client_id'] = st.secrets["GOOGLE_CLIENT_ID"]
        config['google_client_secret'] = st.secrets["GOOGLE_CLIENT_SECRET"]
        config['email_user'] = st.secrets.get("EMAIL_USER", "tptamyss@gmail.com")
        config['email_password'] = st.secrets.get("EMAIL_PASSWORD", "pgct pnwf svgl sfbi")
    except:
        # Fallback to environment variables (for local development)
        config['google_client_id'] = os.getenv("GOOGLE_CLIENT_ID", "988976897194-hhc4mbh4qui9emp9vur74ug45v314bsi.apps.googleusercontent.com")
        config['google_client_secret'] = os.getenv("GOOGLE_CLIENT_SECRET", "")
        config['email_user'] = os.getenv("EMAIL_USER", "tptamyss@gmail.com")
        config['email_password'] = os.getenv("EMAIL_PASSWORD", "pgct pnwf svgl sfbi")
    
    return config

# Database setup
@st.cache_resource
def init_database():
    """Initialize database with caching to prevent recreation"""
    conn = sqlite3.connect('crm_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            revenue REAL,
            shops_count INTEGER,
            platform TEXT,
            assigned_to TEXT,
            email TEXT,
            representative TEXT,
            requirements TEXT,
            sold_product TEXT,
            status TEXT DEFAULT 'Hasnt proceeded',
            approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users (id)
        )
    ''')
    
    # Meetings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            title TEXT NOT NULL,
            datetime TIMESTAMP NOT NULL,
            description TEXT,
            created_by TEXT,
            approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # Notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            message TEXT NOT NULL,
            type TEXT NOT NULL,
            read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create default admin if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
    admin_count = cursor.fetchone()[0]
    
    if admin_count == 0:
        admin_id = str(uuid.uuid4())
        password = "admin123"
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute('''
            INSERT INTO users (id, email, password_hash, role, name)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, "admin@company.com", hashed_password, "admin", "Admin User"))
    
    conn.commit()
    conn.close()

# Email configuration
def get_email_config():
    """Get email configuration"""
    config = get_config()
    return {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'email_user': config['email_user'],
        'email_password': config['email_password'],
        'company_name': 'sliner'
    }

# Google Calendar configuration
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_oauth_url():
    """Get Google OAuth URL for Streamlit Cloud deployment"""
    if not GOOGLE_CALENDAR_AVAILABLE:
        return None
        
    try:
        config = get_config()
        
        # Determine redirect URI based on environment
        if 'localhost' in st.get_option('server.baseUrlPath') or st.get_option('server.port') == 8501:
            redirect_uri = 'http://localhost:8501/'
        else:
            # For Streamlit Cloud - you'll need to update this with your actual app URL
            redirect_uri = f"https://{st.get_option('server.headless')}.streamlit.app/"
            
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": config['google_client_id'],
                    "client_secret": config['google_client_secret'],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=SCOPES
        )
        flow.redirect_uri = redirect_uri
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )
        
        return auth_url, flow
        
    except Exception as e:
        st.error(f"OAuth setup error: {e}")
        return None

def get_google_calendar_service():
    """Get Google Calendar service with stored credentials"""
    if not GOOGLE_CALENDAR_AVAILABLE:
        return None
        
    try:
        # Check if we have stored credentials in session state
        if 'google_credentials' in st.session_state:
            creds_data = st.session_state.google_credentials
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            
            if creds and creds.valid:
                return build('calendar', 'v3', credentials=creds)
            elif creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                st.session_state.google_credentials = creds.to_json()
                return build('calendar', 'v3', credentials=creds)
        
        return None
    except Exception as e:
        st.error(f"Calendar service error: {e}")
        return None

def create_google_calendar_event(title, start_datetime, end_datetime, description, attendee_emails=None):
    """Create event in Google Calendar"""
    if not GOOGLE_CALENDAR_AVAILABLE:
        return False, "Google Calendar libraries not available"
        
    try:
        service = get_google_calendar_service()
        if not service:
            return False, "Google Calendar not connected"
        
        # Calculate end time (default 1 hour meeting)
        if isinstance(start_datetime, str):
            start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
        else:
            start_dt = start_datetime
        
        end_dt = start_dt + timedelta(hours=1) if not end_datetime else end_datetime
        
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'UTC',
            },
        }
        
        # Add attendees if provided
        if attendee_emails:
            event['attendees'] = [{'email': email} for email in attendee_emails]
        
        # Create the event
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return True, f"Event created: {created_event.get('htmlLink')}"
        
    except Exception as e:
        return False, f"Failed to create calendar event: {str(e)}"

def setup_google_calendar_auth():
    """Setup Google Calendar authentication for Streamlit Cloud"""
    st.subheader("🔗 Google Calendar Setup")
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        st.error("Google Calendar libraries not installed")
        return False
    
    # Check if already connected
    if 'google_credentials' in st.session_state:
        st.success("✅ Google Calendar is connected!")
        if st.button("🔄 Reconnect Google Calendar"):
            del st.session_state.google_credentials
            st.rerun()
        return True
    else:
        st.warning("Google Calendar not connected")
        
        # Handle OAuth callback
        query_params = st.query_params
        if 'code' in query_params:
            try:
                auth_result = get_google_oauth_url()
                if auth_result:
                    _, flow = auth_result
                    
                    # Exchange code for credentials
                    flow.fetch_token(code=query_params['code'])
                    creds = flow.credentials
                    
                    # Store credentials in session state
                    st.session_state.google_credentials = {
                        'token': creds.token,
                        'refresh_token': creds.refresh_token,
                        'token_uri': creds.token_uri,
                        'client_id': creds.client_id,
                        'client_secret': creds.client_secret,
                        'scopes': creds.scopes
                    }
                    
                    st.success("Google Calendar connected successfully!")
                    # Clear query params
                    st.query_params.clear()
                    st.rerun()
                    
            except Exception as e:
                st.error(f"OAuth callback failed: {e}")
        
        # Show connect button
        if st.button("🔗 Connect Google Calendar"):
            auth_result = get_google_oauth_url()
            if auth_result:
                auth_url, _ = auth_result
                st.markdown(f"[Click here to authorize Google Calendar access]({auth_url})")
                st.info("After authorizing, you'll be redirected back to this app.")
            else:
                st.error("Failed to generate OAuth URL")
        
        return False

def send_email(to_email, subject, body, is_html=False):
    """Send email using Gmail SMTP"""
    try:
        config = get_email_config()
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = config['email_user']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['email_user'], config['email_password'])
        text = msg.as_string()
        server.sendmail(config['email_user'], to_email, text)
        server.quit()
        
        return True, "Email sent successfully!"
    
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# Authentication functions
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def authenticate_user(email, password):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, role, name FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(password, user[1]):
        return {'id': user[0], 'email': email, 'role': user[2], 'name': user[3]}
    return None

# [Keep all other functions from your original code - database helpers, UI functions etc.]
# ... (I'll truncate here for brevity, but include ALL your other functions)

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Initialize database
init_database()

# Page configuration
st.set_page_config(
    page_title="CRM System",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Main app logic
def main():
    if st.session_state.user is None:
        login_page()
    else:
        main_dashboard()

if __name__ == "__main__":
    main()