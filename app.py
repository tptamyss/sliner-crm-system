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


# Database setup
def init_database():
    conn = sqlite3.connect('crm_database.db')
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
        st.success("Default admin created - Email: admin@company.com, Password: admin123")
    
    conn.commit()
    conn.close()

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

    # Email configuration
def get_email_config():
    """Get email configuration"""
    return {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'email_user': "tptamyss@gmail.com",  # Replace with actual
        'email_password': "pgct pnwf svgl sfbi",  # Replace with actual
        'company_name': 'sliner'
    }


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

# Database helper functions
def get_all_users():
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('SELECT id, name, email, role FROM users', conn)
    conn.close()
    return df

def add_user(email, password, role, name):
    try:
        conn = sqlite3.connect('crm_database.db')
        cursor = conn.cursor()
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(password)
        cursor.execute('''
            INSERT INTO users (id, email, password_hash, role, name)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, email, hashed_password, role, name))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def get_customers(user_id=None, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT c.*, u.name as assigned_name 
            FROM customers c 
            LEFT JOIN users u ON c.assigned_to = u.id 
            WHERE c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn)
    else:
        query = '''
            SELECT c.*, u.name as assigned_name 
            FROM customers c 
            LEFT JOIN users u ON c.assigned_to = u.id 
            WHERE c.assigned_to = ? AND c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def add_customer(name, revenue, shops_count, platform, assigned_to, email, representative, requirements, sold_product, created_by, auto_approve=False):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    customer_id = str(uuid.uuid4())
    approved = auto_approve
    
    cursor.execute('''
        INSERT INTO customers (id, name, revenue, shops_count, platform, assigned_to, email, representative, requirements, sold_product, approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (customer_id, name, revenue, shops_count, platform, assigned_to, email, representative, requirements, sold_product, approved))
    
    # Create notification for admin if not auto-approved
    if not auto_approve:
        notification_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO notifications (id, user_id, message, type)
            VALUES (?, ?, ?, ?)
        ''', (notification_id, None, f"New customer '{name}' needs approval", "customer_approval"))
    
    conn.commit()
    conn.close()

def update_customer_status(customer_id, new_status):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE customers SET status = ? WHERE id = ?', (new_status, customer_id))
    conn.commit()
    conn.close()

def update_customer(customer_id, name, revenue, shops_count, platform, assigned_to, email, representative, requirements, sold_product, status):
    """Update customer details"""
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE customers
        SET name=?, revenue=?, shops_count=?, platform=?, assigned_to=?, email=?, representative=?, 
            requirements=?, sold_product=?, status=?
        WHERE id=?
    ''', (name, revenue, shops_count, platform, assigned_to, email, representative, requirements, sold_product, status, customer_id))
    conn.commit()
    conn.close()

def delete_customer(customer_id):
    """Delete customer by ID"""
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM customers WHERE id=?', (customer_id,))
    conn.commit()
    conn.close()

def get_pending_customers():
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('''
        SELECT c.*, u.name as assigned_name 
        FROM customers c 
        LEFT JOIN users u ON c.assigned_to = u.id 
        WHERE c.approved = FALSE
    ''', conn)
    conn.close()
    return df

def approve_customer(customer_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE customers SET approved = TRUE WHERE id = ?', (customer_id,))
    conn.commit()
    conn.close()

# Meeting functions
def add_meeting(customer_id, title, datetime_obj, description, created_by, auto_approve=False):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    meeting_id = str(uuid.uuid4())
    approved = auto_approve

    # Insert the meeting into the DB
    cursor.execute('''
        INSERT INTO meetings (id, customer_id, title, datetime, description, created_by, approved)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (meeting_id, customer_id, title, datetime_obj, description, created_by, approved))

    # If not auto-approved → notify admin
    if not auto_approve:
        notification_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO notifications (id, user_id, message, type)
            VALUES (?, ?, ?, ?)
        ''', (notification_id, None, f"New meeting '{title}' needs approval", "meeting_approval"))

    # If approved → notify the assigned employee
    if approved:
        cursor.execute('SELECT assigned_to, name FROM customers WHERE id = ?', (customer_id,))
        customer_info = cursor.fetchone()
        if customer_info and customer_info[0]:
            notification_id = str(uuid.uuid4())
            meeting_time = datetime_obj.strftime('%B %d, %Y at %I:%M %p')
            cursor.execute('''
                INSERT INTO notifications (id, user_id, message, type)
                VALUES (?, ?, ?, ?)
            ''', (notification_id, customer_info[0], f"New meeting scheduled: {title} on {meeting_time}", "meeting_scheduled"))

    conn.commit()
    conn.close()

def get_meetings(user_id=None, user_role=None, view_option="All Upcoming"):
    conn = sqlite3.connect('crm_database.db')
    
    # Base query with joins
    base_query = '''
        SELECT m.*, c.name as customer_name, u.name as created_by_name
        FROM meetings m
        JOIN customers c ON m.customer_id = c.id
        JOIN users u ON m.created_by = u.id
        WHERE m.approved = TRUE AND m.datetime >= datetime('now')
    '''
    
    # Add user filtering
    if user_role != 'admin':
        base_query += f" AND c.assigned_to = '{user_id}'"
    
    # Add time filtering
    if view_option == "This Week":
        base_query += " AND m.datetime <= datetime('now', '+7 days')"
    elif view_option == "This Month":
        base_query += " AND m.datetime <= datetime('now', '+30 days')"
    
    base_query += " ORDER BY m.datetime ASC"
    
    df = pd.read_sql_query(base_query, conn)
    conn.close()
    return df

def get_pending_meetings():
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('''
        SELECT m.*, c.name as customer_name, u.name as created_by_name
        FROM meetings m
        JOIN customers c ON m.customer_id = c.id
        JOIN users u ON m.created_by = u.id
        WHERE m.approved = FALSE
        ORDER BY m.datetime ASC
    ''', conn)
    conn.close()
    return df

def approve_meeting(meeting_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE meetings SET approved = TRUE WHERE id = ?', (meeting_id,))
    
    # Get meeting info and create notification for assigned employee
    cursor.execute('''
        SELECT m.title, m.datetime, c.assigned_to, c.name
        FROM meetings m
        JOIN customers c ON m.customer_id = c.id
        WHERE m.id = ?
    ''', (meeting_id,))
    
    meeting_info = cursor.fetchone()
    if meeting_info and meeting_info[2]:  # If there's an assigned employee
        notification_id = str(uuid.uuid4())
        meeting_time = meeting_info[1]  # datetime is already a string from SQLite
        cursor.execute('''
            INSERT INTO notifications (id, user_id, message, type)
            VALUES (?, ?, ?, ?)
        ''', (notification_id, meeting_info[2], f"Meeting approved: {meeting_info[0]} on {meeting_time}", "meeting_approved"))
    
    conn.commit()
    conn.close()

def send_meeting_notification(meeting_id, notification_type="reminder"):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    # Get meeting and customer info
    cursor.execute('''
        SELECT m.title, m.datetime, c.assigned_to, c.name, c.representative, c.email, u.name, u.email
        FROM meetings m
        JOIN customers c ON m.customer_id = c.id
        JOIN users u ON c.assigned_to = u.id
        WHERE m.id = ?
    ''', (meeting_id,))
    
    meeting_info = cursor.fetchone()
    if meeting_info:
        meeting_title, meeting_datetime, assigned_to, customer_name, customer_rep, customer_email, employee_name, employee_email = meeting_info
        
        # Create in-app notification
        notification_id = str(uuid.uuid4())
        if notification_type == "reminder":
            message = f"Reminder: Meeting '{meeting_title}' with {customer_name} on {meeting_datetime}"
        else:
            message = f"Meeting scheduled: '{meeting_title}' with {customer_name} on {meeting_datetime}"
        
        cursor.execute('''
            INSERT INTO notifications (id, user_id, message, type)
            VALUES (?, ?, ?, ?)
        ''', (notification_id, assigned_to, message, f"meeting_{notification_type}"))
        
        # Send actual email
        if employee_email:
            email_subject = f"Meeting {notification_type.title()}: {meeting_title}"
            email_body = f"""
Dear {employee_name},

This is a {notification_type} for your upcoming meeting:

Meeting: {meeting_title}
Customer: {customer_name}
Representative: {customer_rep}
Date & Time: {meeting_datetime}
Customer Email: {customer_email}

Please make sure to prepare for this meeting.

Best regards,
CRM System
            """
            
            success, result = send_email(employee_email, email_subject, email_body)
            if success:
                # Add success notification
                success_notif_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO notifications (id, user_id, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (success_notif_id, assigned_to, f"Email sent successfully for meeting: {meeting_title}", "email_sent"))
    conn.commit()
    conn.close()
    return success, result if 'success' in locals() else (True, "Notification created")

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Initialize database
init_database()

# Login page
def login_page():
    st.title("🏢 CRM System - Login")
    
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            user = authenticate_user(email, password)
            if user:
                st.session_state.user = user
                st.session_state.page = 'main'
                st.rerun()
            else:
                st.error("Invalid email or password")

# Main dashboard
def main_dashboard():
    st.title(f"Welcome, {st.session_state.user['name']}")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    if st.sidebar.button("🏠 Main Dashboard"):
        st.session_state.page = 'main'
    if st.sidebar.button("📅 Calendar"):
        st.session_state.page = 'calendar'
    unread_count = get_unread_count(st.session_state.user['id'], st.session_state.user['role'])
    if unread_count > 0:
        notification_label = f"🔔 Notifications ({unread_count})"
    else:
        notification_label = "🔔 Notifications"
        
    if st.sidebar.button(notification_label):
        st.session_state.page = 'notifications'
    if st.session_state.user['role'] == 'admin':
        if st.sidebar.button("👥 User Management"):
            st.session_state.page = 'users'
        if st.sidebar.button("✅ Approvals"):
            st.session_state.page = 'approvals'
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout"):
        st.session_state.user = None
        st.session_state.page = 'login'
        st.rerun()
    
    # Main content based on page
    if st.session_state.page == 'main':
        show_main_dashboard()
    elif st.session_state.page == 'calendar':
        show_calendar()
    elif st.session_state.page == 'notifications':
        show_notifications()
    elif st.session_state.page == 'users' and st.session_state.user['role'] == 'admin':
        show_user_management()
    elif st.session_state.page == 'approvals' and st.session_state.user['role'] == 'admin':
        show_approvals()

def show_main_dashboard():
    st.header("📊 Customer Management")
    
    # Add new customer section
    with st.expander("➕ Add New Customer"):
        with st.form("add_customer"):
            col1, col2 = st.columns(2)
            
            with col1:
                customer_name = st.text_input("Customer Name*")
                revenue = st.number_input("Revenue ($)", min_value=0.0, format="%.2f")
                shops_count = st.number_input("Number of Shops", min_value=0)
                platform = st.text_input("Platform")
            
            with col2:
                # Get users for assignment
                users_df = get_all_users()
                employee_users = users_df[users_df['role'] == 'employee']
                if len(employee_users) > 0:
                    assigned_to = st.selectbox("Assign to Employee", 
                                             options=employee_users['id'].tolist(),
                                             format_func=lambda x: employee_users[employee_users['id']==x]['name'].iloc[0])
                else:
                    st.warning("No employees available. Admin should add employees first.")
                    assigned_to = None
                
                customer_email = st.text_input("Customer Email")
                representative = st.text_input("Representative Person")
            
            requirements = st.text_area("Requirements")
            sold_product = st.text_input("Sold Product")
            
            submit_customer = st.form_submit_button("Add Customer")
            
            if submit_customer:
                if not customer_name:
                    st.error("Customer Name is required!")
                elif not assigned_to:
                    st.error("Please assign to an employee!")
                else:
                    try:
                        auto_approve = st.session_state.user['role'] == 'admin'
                        add_customer(customer_name, revenue, shops_count, platform, assigned_to, 
                                   customer_email, representative, requirements, sold_product, 
                                   st.session_state.user['id'], auto_approve)
                        
                        if auto_approve:
                            st.success("✅ Customer added successfully and visible immediately!")
                        else:
                            st.success("📤 Customer submitted for admin approval! Check 'Approvals' section.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding customer: {str(e)}")
    
    # Display customers
    st.subheader("Customer List")
    
    # View options
    view_type = st.radio("View Type", ["Table", "Cards"], horizontal=True)
    
    customers_df = get_customers(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(customers_df) > 0:
        if view_type == "Table":
            # Status update functionality
            status_options = ["Hasn't proceeded", "Ongoing", "Dealt", "Cancelled"]
            
            for idx, customer in customers_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.write(f"**{customer['name']}** - {customer['platform']}")
                        st.write(f"Revenue: ${customer['revenue']:,.2f} | Shops: {customer['shops_count']}")
                    
                    with col2:
                        st.write(f"Assigned: {customer['assigned_name']}")
                        st.write(f"Rep: {customer['representative']}")
                    
                    with col3:
                        # Only allow status change if user is assigned or admin
                        can_edit = (st.session_state.user['role'] == 'admin' or 
                                  customer['assigned_to'] == st.session_state.user['id'])
                        
                        if can_edit:
                            current_status = customer['status']
                            new_status = st.selectbox(
                                "Status",
                                status_options,
                                index=status_options.index(current_status) if current_status in status_options else 0,
                                key=f"status_{customer['id']}"
                            )
                            
                            if new_status != current_status:
                                update_customer_status(customer['id'], new_status)
                                st.rerun()
                        else:
                            st.write(f"Status: {customer['status']}")
                    
                    st.divider()
        
        else:  # Cards view
            cols = st.columns(3)
            for idx, customer in customers_df.iterrows():
                with cols[idx % 3]:
                    with st.container():
                        st.markdown(f"""
                        <div style="border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin: 10px 0;">
                            <h4>{customer['name']}</h4>
                            <p><b>Platform:</b> {customer['platform']}</p>
                            <p><b>Revenue:</b> ${customer['revenue']:,.2f}</p>
                            <p><b>Shops:</b> {customer['shops_count']}</p>
                            <p><b>Status:</b> {customer['status']}</p>
                            <p><b>Assigned:</b> {customer['assigned_name']}</p>
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("No customers found. Add your first customer above!")

def show_calendar():
    st.header("📅 Calendar & Meetings")
    
    # Add new meeting section
    with st.expander("➕ Schedule New Meeting"):
        with st.form("add_meeting"):
            col1, col2 = st.columns(2)
            
            with col1:
                meeting_title = st.text_input("Meeting Title*")
                
                # Get customers for meeting selection
                customers_df = get_customers(st.session_state.user['id'], st.session_state.user['role'])
                if len(customers_df) > 0:
                    customer_id = st.selectbox("Customer", 
                                             options=customers_df['id'].tolist(),
                                             format_func=lambda x: customers_df[customers_df['id']==x]['name'].iloc[0])
                else:
                    st.warning("No customers available. Add customers first.")
                    customer_id = None
                
                meeting_date = st.date_input("Meeting Date", 
                                           min_value=datetime.now().date())
            
            with col2:
                meeting_time = st.time_input("Meeting Time")
                meeting_description = st.text_area("Meeting Description")
            
            submit_meeting = st.form_submit_button("Schedule Meeting")
            
            if submit_meeting:
                if not meeting_title:
                    st.error("Meeting Title is required!")
                elif not customer_id:
                    st.error("Please select a customer!")
                else:
                   meeting_datetime = datetime.combine(meeting_date, meeting_time)
                   auto_approve = st.session_state.user['role'] == 'admin'
                   add_meeting(customer_id, meeting_title, meeting_datetime, meeting_description, 
                             st.session_state.user['id'], auto_approve)
                
                   if auto_approve:
                       st.success("✅ Meeting scheduled successfully!")
                   else:
                       st.success("📤 Meeting submitted for admin approval!")
                   st.rerun()
    
    # Display meetings
    st.subheader("Upcoming Meetings")
    
    # View options
    view_option = st.radio("View", ["This Week", "This Month", "All Upcoming"], horizontal=True)
    
    meetings_df = get_meetings(st.session_state.user['id'], st.session_state.user['role'], view_option)
    
    if len(meetings_df) > 0:
        # Group meetings by date
        meetings_df['date'] = pd.to_datetime(meetings_df['datetime']).dt.date
        meetings_df['time'] = pd.to_datetime(meetings_df['datetime']).dt.time
        
        for date, day_meetings in meetings_df.groupby('date'):
            st.subheader(f"📅 {date.strftime('%A, %B %d, %Y')}")
            
            for _, meeting in day_meetings.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**🕐 {meeting['time'].strftime('%I:%M %p')}**")
                        st.write(f"**{meeting['title']}**")
                        st.write(f"Customer: {meeting['customer_name']}")
                    
                    with col2:
                        st.write(f"Created by: {meeting['created_by_name']}")
                        if meeting['description']:
                            st.write(f"Notes: {meeting['description']}")
                    
                    with col3:
                        if st.button("📧 Notify", key=f"notify_{meeting['id']}"):
                            success, message = send_meeting_notification(meeting['id'])
                            if success:
                                st.success("Email notification sent!")
                            else:
                                st.error(f"Failed to send email: {message}")
                            st.rerun()
                
                st.divider()
    else:
        st.info("No upcoming meetings. Schedule your first meeting above!")
    
    # Quick stats
    st.subheader("📊 Meeting Statistics")
    col1, col2, col3 = st.columns(3)
    
    if len(meetings_df) > 0:
        with col1:
            today_meetings = len(meetings_df[meetings_df['date'] == datetime.now().date()])
            st.metric("Today", today_meetings)
    
        with col2:
            week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            week_end = week_start + timedelta(days=6)
            week_meetings = len(meetings_df[
                (meetings_df['date'] >= week_start) & (meetings_df['date'] <= week_end)
            ])
            st.metric("This Week", week_meetings)
    
        with col3:
            month_meetings = len(meetings_df[
                meetings_df['date'].apply(lambda x: x.month == datetime.now().month and x.year == datetime.now().year)
            ])
            st.metric("This Month", month_meetings)
    else:
        with col1:
            st.metric("Today", 0)
        with col2:
            st.metric("This Week", 0)
        with col3:
            st.metric("This Month", 0)

def show_notifications():
    st.header("🔔 Notifications")
    
    # Get notifications
    notifications_df = get_notifications(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(notifications_df) > 0:
        # Filter options
        filter_option = st.radio("Filter", ["All", "Unread", "Read"], horizontal=True)
        
        if filter_option == "Unread":
            filtered_df = notifications_df[notifications_df['read'] == False]
        elif filter_option == "Read":
            filtered_df = notifications_df[notifications_df['read'] == True]
        else:
            filtered_df = notifications_df
        
        if len(filtered_df) > 0:
            st.write(f"Showing {len(filtered_df)} notifications")
            
            # Mark all as read button
            if len(filtered_df[filtered_df['read'] == False]) > 0:
                if st.button("✅ Mark All as Read"):
                    for _, notif in filtered_df[filtered_df['read'] == False].iterrows():
                        mark_notification_read(notif['id'])
                    st.success("All notifications marked as read!")
                    st.rerun()
            
            st.divider()
            
            # Display notifications
            for _, notification in filtered_df.iterrows():
                with st.container():
                    col1, col2 = st.columns([4, 1])
                    
                    with col1:
                        # Style based on read status
                        if notification['read']:
                            st.write(f"📖 {notification['message']}")
                        else:
                            st.write(f"**📩 {notification['message']}**")
                        
                        # Show timestamp
                        created_time = pd.to_datetime(notification['created_at'])
                        time_ago = datetime.now() - created_time
                        if time_ago.days > 0:
                            time_str = f"{time_ago.days} days ago"
                        elif time_ago.seconds > 3600:
                            time_str = f"{time_ago.seconds // 3600} hours ago"
                        else:
                            time_str = f"{time_ago.seconds // 60} minutes ago"
                        
                        st.caption(f"🕒 {time_str} • Type: {notification['type']}")
                        
                        # Show target user for admin
                        if st.session_state.user['role'] == 'admin' and notification['target_user_name']:
                            st.caption(f"👤 For: {notification['target_user_name']}")
                    
                    with col2:
                        if not notification['read']:
                            if st.button("Mark Read", key=f"read_{notification['id']}"):
                                mark_notification_read(notification['id'])
                                st.rerun()
                    
                    st.divider()
        else:
            st.info(f"No {filter_option.lower()} notifications")
    else:
        st.info("No notifications yet!")
    
    # Quick stats
    if len(notifications_df) > 0:
        st.subheader("📊 Notification Summary")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            unread_count = len(notifications_df[notifications_df['read'] == False])
            st.metric("Unread", unread_count)
        
        with col2:
            read_count = len(notifications_df[notifications_df['read'] == True])
            st.metric("Read", read_count)
        
        with col3:
            total_count = len(notifications_df)
            st.metric("Total", total_count)

def show_user_management():
    st.header("👥 User Management")
    
    # Add new employee
    with st.expander("➕ Add New Employee"):
        with st.form("add_employee"):
            emp_name = st.text_input("Employee Name*")
            emp_email = st.text_input("Employee Email*")
            emp_password = st.text_input("Temporary Password*", type="password")
            
            submit_emp = st.form_submit_button("Add Employee")
            
            if submit_emp and emp_name and emp_email and emp_password:
                if add_user(emp_email, emp_password, "employee", emp_name):
                    st.success("Employee added successfully!")
                    st.rerun()
                else:
                    st.error("Email already exists!")
    st.divider()
    
    # Show all users
    st.subheader("All Users")
    users_df = get_all_users()
    st.dataframe(users_df, use_container_width=True)

def show_approvals():
    st.header("✅ Pending Approvals")
    
    # Customer approvals
    pending_customers = get_pending_customers()
    
    if len(pending_customers) > 0:
        st.subheader("👥 Customer Approvals")
        
        for idx, customer in pending_customers.iterrows():
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**{customer['name']}**")
                    st.write(f"Platform: {customer['platform']} | Revenue: ${customer['revenue']:,.2f}")
                    st.write(f"Assigned to: {customer['assigned_name']}")
                    st.write(f"Requirements: {customer['requirements']}")
                
                with col2:
                    if st.button("✅ Approve", key=f"approve_customer_{customer['id']}"):
                        approve_customer(customer['id'])
                        st.success("Customer approved!")
                        st.rerun()
                    
                    if st.button("❌ Reject", key=f"reject_customer_{customer['id']}"):
                        st.info("Reject functionality coming soon!")
                
                st.divider()
    else:
        st.info("No pending customer approvals!")
    
    st.divider()
    
    # Meeting approvals
    pending_meetings = get_pending_meetings()
    
    if len(pending_meetings) > 0:
        st.subheader("📅 Meeting Approvals")
        
        for idx, meeting in pending_meetings.iterrows():
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    meeting_dt = pd.to_datetime(meeting['datetime'])
                    st.write(f"**{meeting['title']}**")
                    st.write(f"Customer: {meeting['customer_name']}")
                    st.write(f"Date: {meeting_dt.strftime('%A, %B %d, %Y at %I:%M %p')}")
                    st.write(f"Requested by: {meeting['created_by_name']}")
                    if meeting['description']:
                        st.write(f"Description: {meeting['description']}")
                
                with col2:
                    if st.button("✅ Approve", key=f"approve_meeting_{meeting['id']}"):
                        approve_meeting(meeting['id'])
                        st.success("Meeting approved!")
                        st.rerun()
                    
                    if st.button("❌ Reject", key=f"reject_meeting_{meeting['id']}"):
                        st.info("Reject functionality coming soon!")
                
                st.divider()
    else:
        st.info("No pending meeting approvals!")
    
    if len(pending_customers) == 0 and len(pending_meetings) == 0:
        st.success("🎉 All caught up! No pending approvals.")

def get_notifications(user_id, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        # Admin sees all notifications (including system ones with user_id = None)
        query = '''
            SELECT n.*, u.name as target_user_name 
            FROM notifications n 
            LEFT JOIN users u ON n.user_id = u.id 
            ORDER BY n.created_at DESC
        '''
        df = pd.read_sql_query(query, conn)
    else:
        # Employees only see their own notifications
        query = '''
            SELECT n.*, u.name as target_user_name 
            FROM notifications n 
            LEFT JOIN users u ON n.user_id = u.id 
            WHERE n.user_id = ? 
            ORDER BY n.created_at DESC
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def mark_notification_read(notification_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET read = TRUE WHERE id = ?', (notification_id,))
    conn.commit()
    conn.close()

def get_unread_count(user_id, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    if user_role == 'admin':
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE read = FALSE')
    else:
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = FALSE', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# Main app logic
def main():
    if st.session_state.user is None:
        login_page()
    else:
        main_dashboard()

if __name__ == "__main__":
    main()