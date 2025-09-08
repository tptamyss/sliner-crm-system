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

# Configuration for deployment
def get_config():
    """Get configuration from Streamlit secrets or environment variables"""
    config = {}
    try:
        config['email_user'] = st.secrets.get("EMAIL_USER", "tptamyss@gmail.com")
        config['email_password'] = st.secrets.get("EMAIL_PASSWORD", "pgct pnwf svgl sfbi")
    except:
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
    config = get_config()
    return {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'email_user': config['email_user'],
        'email_password': config['email_password'],
        'company_name': 'sliner'
    }

def send_email(to_email, subject, body, is_html=False):
    """Send email using Gmail SMTP"""
    try:
        config = get_email_config()
        
        msg = MIMEMultipart()
        msg['From'] = config['email_user']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['email_user'], config['email_password'])
        text = msg.as_string()
        server.sendmail(config['email_user'], to_email, text)
        server.quit()
        
        return True, "Email sent successfully!"
    
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# Authentication
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

# Notifications helpers
def get_unread_count(user_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = 0', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_notifications(user_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, message, type, read, created_at 
        FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,))
    notifications = cursor.fetchall()
    conn.close()
    return notifications

def show_notifications():
    user = st.session_state.user
    if not user:
        st.info("Please log in to see notifications.")
        return

    notifications = get_notifications(user["id"])
    st.subheader("🔔 Notifications")

    if not notifications:
        st.write("No notifications yet.")
    else:
        for notif in notifications:
            notif_id, message, notif_type, read, created_at = notif
            color = "green" if notif_type == "success" else "red" if notif_type == "error" else "blue"

            st.markdown(
                f"<div style='padding:8px; margin:4px; border-radius:5px; background-color:{color}; color:white;'>"
                f"{message} <br><small>{created_at}</small></div>",
                unsafe_allow_html=True
            )

        if st.button("Mark all as read"):
            conn = sqlite3.connect('crm_database.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE notifications SET read = 1 WHERE user_id = ?', (user["id"],))
            conn.commit()
            conn.close()
            st.rerun()

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Initialize database
init_database()

# Page config
st.set_page_config(
    page_title="CRM System",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Placeholder pages
def login_page():
    st.title("Login Page")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(email, password)
        if user:
            st.session_state.user = user
            st.session_state.page = "dashboard"
            st.rerun()
        else:
            st.error("Invalid credentials")

def main_dashboard():
    st.title("Main Dashboard")
    st.write(f"Welcome, {st.session_state.user['name']}!")
    if st.button("Log out"):
        st.session_state.user = None
        st.session_state.page = "login"
        st.rerun()

# Main app
def main():
    if st.session_state.user is None:
        login_page()
    else:
        main_dashboard()

if __name__ == "__main__":
    main()
