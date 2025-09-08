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


# ==============================
# Configuration
# ==============================
def get_config():
    config = {}
    try:
        config['google_client_id'] = st.secrets["GOOGLE_CLIENT_ID"]
        config['google_client_secret'] = st.secrets["GOOGLE_CLIENT_SECRET"]
        config['email_user'] = st.secrets.get("EMAIL_USER", "tptamyss@gmail.com")
        config['email_password'] = st.secrets.get("EMAIL_PASSWORD", "pgct pnwf svgl sfbi")
    except:
        config['google_client_id'] = os.getenv("GOOGLE_CLIENT_ID", "")
        config['google_client_secret'] = os.getenv("GOOGLE_CLIENT_SECRET", "")
        config['email_user'] = os.getenv("EMAIL_USER", "tptamyss@gmail.com")
        config['email_password'] = os.getenv("EMAIL_PASSWORD", "pgct pnwf svgl sfbi")
    return config


# ==============================
# Database setup
# ==============================
@st.cache_resource
def init_database():
    conn = sqlite3.connect('crm_database.db', check_same_thread=False)
    cursor = conn.cursor()

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

    # Create default admin
    cursor.execute('SELECT COUNT(*) FROM users WHERE role="admin"')
    if cursor.fetchone()[0] == 0:
        admin_id = str(uuid.uuid4())
        hashed_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        cursor.execute('''
            INSERT INTO users (id, email, password_hash, role, name)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, "admin@company.com", hashed_password, "admin", "Admin User"))

    conn.commit()
    conn.close()


# ==============================
# Email utilities
# ==============================
def get_email_config():
    config = get_config()
    return {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'email_user': config['email_user'],
        'email_password': config['email_password'],
        'company_name': 'sliner'
    }

def send_email(to_email, subject, body, is_html=False):
    try:
        config = get_email_config()
        msg = MIMEMultipart()
        msg['From'] = config['email_user']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['email_user'], config['email_password'])
        server.sendmail(config['email_user'], to_email, msg.as_string())
        server.quit()
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


# ==============================
# Google Calendar utilities
# ==============================
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_oauth_url():
    if not GOOGLE_CALENDAR_AVAILABLE: return None
    try:
        config = get_config()
        redirect_uri = "https://your-app-name.streamlit.app/"
        flow = Flow.from_client_config(
            {"web": {
                "client_id": config['google_client_id'],
                "client_secret": config['google_client_secret'],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }},
            scopes=SCOPES
        )
        flow.redirect_uri = redirect_uri
        auth_url, _ = flow.authorization_url(access_type='offline', prompt='consent')
        return auth_url, flow
    except Exception as e:
        st.error(f"OAuth setup error: {e}")
        return None

def get_google_calendar_service():
    if not GOOGLE_CALENDAR_AVAILABLE: return None
    try:
        if 'google_credentials' in st.session_state:
            creds_data = st.session_state.google_credentials
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            if creds.valid:
                return build('calendar', 'v3', credentials=creds)
            elif creds.expired and creds.refresh_token:
                creds.refresh(Request())
                st.session_state.google_credentials = creds.to_json()
                return build('calendar', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"Calendar service error: {e}")
        return None


# ==============================
# Authentication
# ==============================
def hash_password(password): return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
def verify_password(password, hashed): return bcrypt.checkpw(password.encode('utf-8'), hashed)

def authenticate_user(email, password):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, role, name FROM users WHERE email=?', (email,))
    user = cursor.fetchone()
    conn.close()
    if user and verify_password(password, user[1]):
        return {'id': user[0], 'email': email, 'role': user[2], 'name': user[3]}
    return None


# ==============================
# UI Pages
# ==============================
def login_page():
    st.title("🔑 Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(email, password)
        if user:
            st.session_state.user = user
            st.success(f"Welcome back, {user['name']}!")
            st.session_state.page = "dashboard"
            st.rerun()
        else:
            st.error("Invalid email or password.")
    st.caption("Default admin login: **admin@company.com / admin123**")

def main_dashboard():
    st.title("🏢 CRM Dashboard")
    st.write(f"Hello, **{st.session_state.user['name']}** 👋")
    st.write("This is your CRM main dashboard.")

def google_calendar_setup():
    st.subheader("🔗 Google Calendar Setup")
    if not GOOGLE_CALENDAR_AVAILABLE:
        st.error("Google Calendar libraries not installed")
        return
    if 'google_credentials' in st.session_state:
        st.success("✅ Google Calendar is connected!")
    else:
        if st.button("Connect Google Calendar"):
            auth_result = get_google_oauth_url()
            if auth_result:
                auth_url, _ = auth_result
                st.markdown(f"[Click here to authorize Google Calendar access]({auth_url})")
            else:
                st.error("Failed to generate OAuth URL")


# ==============================
# App Entry
# ==============================
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = 'login'
init_database()

st.set_page_config(page_title="CRM System", page_icon="🏢", layout="wide")

def main():
    if st.session_state.user is None:
        login_page()
    else:
        choice = st.sidebar.radio("Navigation", ["Dashboard", "Google Calendar"])
        if choice == "Dashboard":
            main_dashboard()
        elif choice == "Google Calendar":
            google_calendar_setup()

if __name__ == "__main__":
    main()
