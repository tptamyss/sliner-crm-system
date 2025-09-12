import streamlit as st
import sqlite3
import bcrypt
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def init_database():
    """Initialize database with proper error handling and recovery"""
    db_path = 'crm_database.db'
    max_retries = 2
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Enable foreign keys
            cursor.execute('PRAGMA foreign_keys = ON')
            
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
            
            # Enhanced Customers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    CustomerID TEXT PRIMARY KEY,
                    CompanyName TEXT NOT NULL,
                    TaxCode TEXT,
                    GroupID TEXT,
                    Address TEXT,
                    Country TEXT DEFAULT 'Vietnam',
                    CustomerCategory TEXT CHECK (CustomerCategory IN ('I', 'H', 'C')),
                    CustomerType TEXT,
                    ContactPerson1 TEXT,
                    ContactEmail1 TEXT,
                    ContactPhone1 TEXT,
                    ContactPerson2 TEXT,
                    ContactEmail2 TEXT,
                    ContactPhone2 TEXT,
                    Industry TEXT,
                    Source TEXT,
                    assigned_to TEXT,
                    status TEXT DEFAULT 'Chưa bắt đầu',
                    approved BOOLEAN DEFAULT FALSE,
                    CreatedDate DATE DEFAULT (date('now')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (assigned_to) REFERENCES users (id)
                )
            ''')
            
            # Services table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    ServiceID TEXT PRIMARY KEY,
                    CustomerID TEXT NOT NULL,
                    ServiceType TEXT,
                    Description TEXT,
                    StartDate DATE,
                    ExpectedEndDate DATE,
                    Status TEXT DEFAULT 'Chưa bắt đầu',
                    PackageCode TEXT,
                    Partner TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (CustomerID) REFERENCES customers (CustomerID)
                )
            ''')
            
            # Payments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    PaymentID TEXT PRIMARY KEY,
                    ServiceID TEXT NOT NULL,
                    Currency TEXT DEFAULT 'VND',
                    OriginalAmount DECIMAL(18,2),
                    ExchangeRate DECIMAL(10,4),
                    ConvertedAmount DECIMAL(18,2),
                    DepositAmount DECIMAL(18,2) DEFAULT 0,
                    DepositDate DATE,
                    FirstPaymentAmount DECIMAL(18,2) DEFAULT 0,
                    FirstPaymentDate DATE,
                    SecondPaymentAmount DECIMAL(18,2) DEFAULT 0,
                    SecondPaymentDate DATE,
                    Notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ServiceID) REFERENCES services (ServiceID)
                )
            ''')
            
            # Work Progress table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_progress (
                    TaskID TEXT PRIMARY KEY,
                    ServiceID TEXT NOT NULL,
                    TaskName TEXT NOT NULL,
                    TaskDescription TEXT,
                    StartDate DATE,
                    ExpectedEndDate DATE,
                    Status TEXT DEFAULT 'Chưa bắt đầu',
                    LastUpdated DATE DEFAULT (date('now')),
                    UpdatedBy TEXT,
                    Notes TEXT,
                    Progress INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ServiceID) REFERENCES services (ServiceID),
                    FOREIGN KEY (UpdatedBy) REFERENCES users (id)
                )
            ''')
            
            # Work Billing table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_billing (
                    BillingID TEXT PRIMARY KEY,
                    ServiceID TEXT NOT NULL,
                    ActivityType TEXT,
                    Level TEXT,
                    HoursWorked DECIMAL(5,2),
                    HourlyRate DECIMAL(18,2),
                    WorkDate DATE,
                    Notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ServiceID) REFERENCES services (ServiceID)
                )
            ''')
            
            # Client Documents table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS client_documents (
                    DocumentID TEXT PRIMARY KEY,
                    CustomerID TEXT NOT NULL,
                    ServiceID TEXT,
                    DocumentType TEXT,
                    DocumentName TEXT,
                    FilePath TEXT,
                    CreatedDate DATE DEFAULT (date('now')),
                    Status TEXT DEFAULT 'Đang xử lý',
                    ResponsiblePerson TEXT,
                    Notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (CustomerID) REFERENCES customers (CustomerID),
                    FOREIGN KEY (ServiceID) REFERENCES services (ServiceID),
                    FOREIGN KEY (ResponsiblePerson) REFERENCES users (id)
                )
            ''')
            
            # Notifications table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    message TEXT NOT NULL,
                    type TEXT NOT NULL,
                    related_id TEXT,
                    read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Customer Groups table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customer_groups (
                    GroupID TEXT PRIMARY KEY,
                    GroupName TEXT NOT NULL,
                    Description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes only after tables are created and committed
            conn.commit()
            
            # Now create indexes
            indexes = [
                'CREATE INDEX IF NOT EXISTS idx_customers_country ON customers(Country)',
                'CREATE INDEX IF NOT EXISTS idx_customers_category ON customers(CustomerCategory)',
                'CREATE INDEX IF NOT EXISTS idx_customers_assigned ON customers(assigned_to)',
                'CREATE INDEX IF NOT EXISTS idx_services_customer ON services(CustomerID)',
                'CREATE INDEX IF NOT EXISTS idx_work_progress_service ON work_progress(ServiceID)',
                'CREATE INDEX IF NOT EXISTS idx_payments_service ON payments(ServiceID)'
            ]
            
            for index_sql in indexes:
                try:
                    cursor.execute(index_sql)
                except sqlite3.Error as index_error:
                    print(f"Warning: Could not create index: {index_error}")
                    # Continue with other indexes
            
            # Create default admin if none exists
            cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
            admin_count = cursor.fetchone()[0]
            
            if admin_count == 0:
                import uuid
                import bcrypt
                admin_id = str(uuid.uuid4())
                password = "admin123"
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                cursor.execute('''
                    INSERT INTO users (id, email, password_hash, role, name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (admin_id, "admin@company.com", hashed_password, "admin", "Admin User"))
            
            # Insert sample customer groups if none exist
            cursor.execute('SELECT COUNT(*) FROM customer_groups')
            group_count = cursor.fetchone()[0]
            if group_count == 0:
                sample_groups = [
                    ('GRP001', 'VIP Customers', 'High priority customers'),
                    ('GRP002', 'Regular Customers', 'Standard customers'),
                    ('GRP003', 'New Leads', 'Potential customers')
                ]
                cursor.executemany('''
                    INSERT INTO customer_groups (GroupID, GroupName, Description)
                    VALUES (?, ?, ?)
                ''', sample_groups)
            
            conn.commit()
            conn.close()
            
            print("Database initialized successfully!")
            return True
            
        except sqlite3.Error as e:
            print(f"Database error on attempt {attempt + 1}: {e}")
            
            # Close connection if it exists
            try:
                conn.close()
            except:
                pass
            
            # If this is not the last attempt, try to recover
            if attempt < max_retries - 1:
                print(f"Attempting to recover database...")
                
                # Check if database file is corrupted
                try:
                    test_conn = sqlite3.connect(db_path)
                    test_conn.execute('PRAGMA integrity_check')
                    test_conn.close()
                except:
                    print("Database appears corrupted, removing and recreating...")
                    if os.path.exists(db_path):
                        os.remove(db_path)
            else:
                print("Failed to initialize database after all attempts")
                return False
        
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    
    return False
# Email configuration
def get_email_config():
    return {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'email_user': "tptamyss@gmail.com",
        'email_password': "pgct pnwf svgl sfbi",
        'company_name': 'CRM System'
    }

def send_email(to_email, subject, body, is_html=False):
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

# Customer ID generation
def generate_customer_id(country, category):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    prefix_map = {
        'Vietnam': 'VND',
        'United States': 'USD', 
        'Singapore': 'SGD',
        'Hong Kong': 'HKD',
        'Japan': 'JPY'
    }
    
    prefix = prefix_map.get(country, 'XXX') + category
    
    cursor.execute('''
        SELECT MAX(CAST(SUBSTR(CustomerID, 5, 6) AS INTEGER)) 
        FROM customers 
        WHERE SUBSTR(CustomerID, 1, 4) = ?
    ''', (prefix,))
    
    result = cursor.fetchone()[0]
    max_id = result if result else 0
    
    new_id = f"{prefix}{str(max_id + 1).zfill(6)}"
    conn.close()
    
    return new_id

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

def get_customer_groups():
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('SELECT * FROM customer_groups', conn)
    conn.close()
    return df

def add_customer_enhanced(company_name, tax_code, group_id, address, country, customer_category, 
                         customer_type, contact_person1, contact_email1, contact_phone1,
                         contact_person2, contact_email2, contact_phone2, industry, source,
                         assigned_to, created_by, auto_approve=False):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    customer_id = generate_customer_id(country, customer_category)
    approved = auto_approve
    
    cursor.execute('''
        INSERT INTO customers (
            CustomerID, CompanyName, TaxCode, GroupID, Address, Country, CustomerCategory, CustomerType,
            ContactPerson1, ContactEmail1, ContactPhone1, ContactPerson2, ContactEmail2, ContactPhone2,
            Industry, Source, assigned_to, approved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (customer_id, company_name, tax_code, group_id, address, country, customer_category, customer_type,
          contact_person1, contact_email1, contact_phone1, contact_person2, contact_email2, contact_phone2,
          industry, source, assigned_to, approved))
    
    if not auto_approve:
        notification_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO notifications (id, user_id, message, type, related_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (notification_id, None, f"New customer '{company_name}' needs approval", "customer_approval", customer_id))
    
    conn.commit()
    conn.close()
    return customer_id

def get_customers_enhanced(user_id=None, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT c.*, u.name as assigned_name, g.GroupName
            FROM customers c 
            LEFT JOIN users u ON c.assigned_to = u.id 
            LEFT JOIN customer_groups g ON c.GroupID = g.GroupID
            WHERE c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn)
    else:
        query = '''
            SELECT c.*, u.name as assigned_name, g.GroupName
            FROM customers c 
            LEFT JOIN users u ON c.assigned_to = u.id 
            LEFT JOIN customer_groups g ON c.GroupID = g.GroupID
            WHERE c.assigned_to = ? AND c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def get_pending_customers():
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('''
        SELECT c.*, u.name as assigned_name, g.GroupName
        FROM customers c 
        LEFT JOIN users u ON c.assigned_to = u.id 
        LEFT JOIN customer_groups g ON c.GroupID = g.GroupID
        WHERE c.approved = FALSE
    ''', conn)
    conn.close()
    return df

def approve_customer(customer_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE customers SET approved = TRUE WHERE CustomerID = ?', (customer_id,))
    conn.commit()
    conn.close()

def update_customer_status(customer_id, new_status):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE customers SET status = ? WHERE CustomerID = ?', (new_status, customer_id))
    conn.commit()
    conn.close()

# Service management functions
def add_service(customer_id, service_type, description, start_date, expected_end_date, package_code, partner):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    service_id = f"DV{str(uuid.uuid4())[:6].upper()}"
    
    cursor.execute('''
        INSERT INTO services (ServiceID, CustomerID, ServiceType, Description, StartDate, ExpectedEndDate, PackageCode, Partner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (service_id, customer_id, service_type, description, start_date, expected_end_date, package_code, partner))
    
    conn.commit()
    conn.close()
    return service_id

def get_services_by_customer(customer_id):
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('SELECT * FROM services WHERE CustomerID = ?', conn, params=(customer_id,))
    conn.close()
    return df

def get_all_services(user_id=None, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT s.*, c.CompanyName, u.name as assigned_name
            FROM services s
            JOIN customers c ON s.CustomerID = c.CustomerID
            LEFT JOIN users u ON c.assigned_to = u.id
            WHERE c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn)
    else:
        query = '''
            SELECT s.*, c.CompanyName, u.name as assigned_name
            FROM services s
            JOIN customers c ON s.CustomerID = c.CustomerID
            LEFT JOIN users u ON c.assigned_to = u.id
            WHERE c.assigned_to = ? AND c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

# Work Progress functions
def add_work_task(service_id, task_name, task_description, start_date, expected_end_date, updated_by):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    task_id = f"CV{str(uuid.uuid4())[:6].upper()}"
    
    cursor.execute('''
        INSERT INTO work_progress (TaskID, ServiceID, TaskName, TaskDescription, StartDate, ExpectedEndDate, UpdatedBy)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, service_id, task_name, task_description, start_date, expected_end_date, updated_by))
    
    conn.commit()
    conn.close()
    return task_id

def get_work_progress(user_id=None, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT wp.*, s.ServiceType, c.CompanyName, u1.name as updated_by_name
            FROM work_progress wp
            JOIN services s ON wp.ServiceID = s.ServiceID
            JOIN customers c ON s.CustomerID = c.CustomerID
            LEFT JOIN users u1 ON wp.UpdatedBy = u1.id
            WHERE c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn)
    else:
        query = '''
            SELECT wp.*, s.ServiceType, c.CompanyName, u1.name as updated_by_name
            FROM work_progress wp
            JOIN services s ON wp.ServiceID = s.ServiceID
            JOIN customers c ON s.CustomerID = c.CustomerID
            LEFT JOIN users u1 ON wp.UpdatedBy = u1.id
            WHERE c.assigned_to = ? AND c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def update_task_status(task_id, new_status, progress, updated_by, notes=""):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE work_progress 
        SET Status = ?, Progress = ?, UpdatedBy = ?, Notes = ?, LastUpdated = date('now')
        WHERE TaskID = ?
    ''', (new_status, progress, updated_by, notes, task_id))
    conn.commit()
    conn.close()

# Payment functions
def add_payment(service_id, currency, original_amount, exchange_rate, deposit_amount=0, notes=""):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    payment_id = f"TT{str(uuid.uuid4())[:6].upper()}"
    converted_amount = original_amount * exchange_rate if exchange_rate else original_amount
    
    cursor.execute('''
        INSERT INTO payments (PaymentID, ServiceID, Currency, OriginalAmount, ExchangeRate, ConvertedAmount, DepositAmount, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (payment_id, service_id, currency, original_amount, exchange_rate, converted_amount, deposit_amount, notes))
    
    conn.commit()
    conn.close()
    return payment_id

def get_payments_by_service(service_id):
    conn = sqlite3.connect('crm_database.db')
    df = pd.read_sql_query('SELECT * FROM payments WHERE ServiceID = ?', conn, params=(service_id,))
    conn.close()
    return df

def update_payment(payment_id, first_amount=None, first_date=None, second_amount=None, second_date=None):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    updates = []
    values = []
    
    if first_amount is not None:
        updates.append('FirstPaymentAmount = ?')
        values.append(first_amount)
    if first_date is not None:
        updates.append('FirstPaymentDate = ?')
        values.append(first_date)
    if second_amount is not None:
        updates.append('SecondPaymentAmount = ?')
        values.append(second_amount)
    if second_date is not None:
        updates.append('SecondPaymentDate = ?')
        values.append(second_date)
    
    if updates:
        values.append(payment_id)
        cursor.execute(f'UPDATE payments SET {", ".join(updates)} WHERE PaymentID = ?', values)
        conn.commit()
    
    conn.close()

# Document functions
def add_document(customer_id, service_id, document_type, document_name, responsible_person, notes=""):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    doc_id = f"DOC{str(uuid.uuid4())[:6].upper()}"
    
    cursor.execute('''
        INSERT INTO client_documents (DocumentID, CustomerID, ServiceID, DocumentType, DocumentName, ResponsiblePerson, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (doc_id, customer_id, service_id, document_type, document_name, responsible_person, notes))
    
    conn.commit()
    conn.close()
    return doc_id

def get_documents(user_id=None, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT cd.*, c.CompanyName, s.ServiceType, u.name as responsible_name
            FROM client_documents cd
            JOIN customers c ON cd.CustomerID = c.CustomerID
            LEFT JOIN services s ON cd.ServiceID = s.ServiceID
            LEFT JOIN users u ON cd.ResponsiblePerson = u.id
            WHERE c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn)
    else:
        query = '''
            SELECT cd.*, c.CompanyName, s.ServiceType, u.name as responsible_name
            FROM client_documents cd
            JOIN customers c ON cd.CustomerID = c.CustomerID
            LEFT JOIN services s ON cd.ServiceID = s.ServiceID
            LEFT JOIN users u ON cd.ResponsiblePerson = u.id
            WHERE c.assigned_to = ? AND c.approved = TRUE
        '''
        df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def update_document_status(doc_id, new_status):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE client_documents SET Status = ? WHERE DocumentID = ?', (new_status, doc_id))
    conn.commit()
    conn.close()

# Notification functions
def get_notifications(user_id, user_role=None):
    conn = sqlite3.connect('crm_database.db')
    if user_role == 'admin':
        query = '''
            SELECT n.*, u.name as target_user_name 
            FROM notifications n 
            LEFT JOIN users u ON n.user_id = u.id 
            ORDER BY n.created_at DESC
        '''
        df = pd.read_sql_query(query, conn)
    else:
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

def mark_notification_read(notification_id):
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET read = TRUE WHERE id = ?', (notification_id,))
    conn.commit()
    conn.close()

def get_dashboard_stats():
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    # Task status counts
    cursor.execute('''
        SELECT Status, COUNT(*) as count
        FROM work_progress
        GROUP BY Status
    ''')
    task_stats = cursor.fetchall()
    
    # Customer progress
    cursor.execute('''
        SELECT c.CustomerID, c.CompanyName, 
               COUNT(wp.TaskID) as total_tasks,
               SUM(CASE WHEN wp.Status = 'Hoàn thành' THEN 1 ELSE 0 END) as completed_tasks
        FROM customers c
        LEFT JOIN services s ON c.CustomerID = s.CustomerID
        LEFT JOIN work_progress wp ON s.ServiceID = wp.ServiceID
        WHERE c.approved = TRUE
        GROUP BY c.CustomerID, c.CompanyName
        HAVING total_tasks > 0
    ''')
    customer_progress = cursor.fetchall()
    
    # Overdue tasks
    cursor.execute('''
        SELECT TaskID, TaskName, Status, LastUpdated
        FROM work_progress
        WHERE Status != 'Hoàn thành' 
        AND date(LastUpdated) < date('now', '-7 days')
    ''')
    overdue_tasks = cursor.fetchall()
    
    conn.close()
    
    return {
        'task_stats': task_stats,
        'customer_progress': customer_progress,
        'overdue_tasks': overdue_tasks
    }

# Session state initialization
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'

# Login page
def login_page():
    st.title("CRM System - Login")
    
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            user = authenticate_user(email, password)
            if user:
                st.session_state.user = user
                st.session_state.page = 'dashboard'
                st.rerun()
            else:
                st.error("Invalid email or password")


# Modified show_customers function with delete functionality
def show_customers():
    st.header("Customer Management")
    
    # Add new customer
    with st.expander("Add New Customer"):
        with st.form("add_customer"):
            col1, col2 = st.columns(2)
            
            with col1:
                company_name = st.text_input("Company Name*")
                tax_code = st.text_input("Tax Code")
                
                # Get customer groups
                groups_df = get_customer_groups()
                if len(groups_df) > 0:
                    group_id = st.selectbox("Customer Group", 
                                          options=[''] + groups_df['GroupID'].tolist(),
                                          format_func=lambda x: groups_df[groups_df['GroupID']==x]['GroupName'].iloc[0] if x else "Select Group")
                else:
                    group_id = st.text_input("Group ID")
                
                address = st.text_area("Address")
                
                country = st.selectbox("Country", 
                                     ['Vietnam', 'United States', 'Singapore', 'Hong Kong', 'Japan'])
                
                customer_category = st.selectbox("Customer Category", 
                                               [('I', 'Individual (Cá nhân)'), 
                                                ('H', 'Household Business (Hộ kinh doanh)'), 
                                                ('C', 'Company (Doanh nghiệp)')],
                                               format_func=lambda x: x[1])
                
                customer_type = st.text_input("Customer Type", 
                                            value=dict([('I', 'Cá nhân'), ('H', 'Hộ kinh doanh'), ('C', 'Doanh nghiệp')])[customer_category[0]])
            
            with col2:
                contact_person1 = st.text_input("Primary Contact Person*")
                contact_email1 = st.text_input("Primary Email")
                contact_phone1 = st.text_input("Primary Phone")
                
                contact_person2 = st.text_input("Secondary Contact Person")
                contact_email2 = st.text_input("Secondary Email")
                contact_phone2 = st.text_input("Secondary Phone")
                
                industry = st.text_input("Industry")
                source = st.selectbox("Source", ['Facebook', 'Website', 'Giới thiệu', 'Google Ads', 'Email Marketing', 'Other'])
                
                # Assign to employee
                users_df = get_all_users()
                employee_users = users_df[users_df['role'] == 'employee']
                if len(employee_users) > 0:
                    assigned_to = st.selectbox("Assign to Employee", 
                                             options=employee_users['id'].tolist(),
                                             format_func=lambda x: employee_users[employee_users['id']==x]['name'].iloc[0])
                else:
                    st.warning("No employees available")
                    assigned_to = None
            
            submit_customer = st.form_submit_button("Add Customer")
            
            if submit_customer:
                if not company_name or not contact_person1:
                    st.error("Company Name and Primary Contact Person are required!")
                elif not assigned_to:
                    st.error("Please assign to an employee!")
                else:
                    auto_approve = st.session_state.user['role'] == 'admin'
                    customer_id = add_customer_enhanced(
                        company_name, tax_code, group_id, address, country, customer_category[0],
                        customer_type, contact_person1, contact_email1, contact_phone1,
                        contact_person2, contact_email2, contact_phone2, industry, source,
                        assigned_to, st.session_state.user['id'], auto_approve
                    )
                    
                    if auto_approve:
                        st.success(f"Customer added successfully! ID: {customer_id}")
                    else:
                        st.success("Customer submitted for admin approval!")
                    st.rerun()
    
    # Display customers
    st.subheader("Customer List")
    
    customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(customers_df) > 0:
        # Filter options
        col1, col2, col3 = st.columns(3)
        with col1:
            category_filter = st.selectbox("Filter by Category", ['All', 'I', 'H', 'C'])
        with col2:
            country_filter = st.selectbox("Filter by Country", ['All'] + list(customers_df['Country'].unique()))
        with col3:
            status_filter = st.selectbox("Filter by Status", ['All'] + list(customers_df['status'].unique()))
        
        # Apply filters
        filtered_df = customers_df.copy()
        if category_filter != 'All':
            filtered_df = filtered_df[filtered_df['CustomerCategory'] == category_filter]
        if country_filter != 'All':
            filtered_df = filtered_df[filtered_df['Country'] == country_filter]
        if status_filter != 'All':
            filtered_df = filtered_df[filtered_df['status'] == status_filter]
        
        # Display customers
        for idx, customer in filtered_df.iterrows():
            with st.expander(f"{customer['CustomerID']} - {customer['CompanyName']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Tax Code:** {customer['TaxCode'] or 'N/A'}")
                    st.write(f"**Address:** {customer['Address'] or 'N/A'}")
                    st.write(f"**Country:** {customer['Country']}")
                    st.write(f"**Category:** {customer['CustomerCategory']} - {customer['CustomerType']}")
                    st.write(f"**Industry:** {customer['Industry'] or 'N/A'}")
                    st.write(f"**Source:** {customer['Source'] or 'N/A'}")
                
                with col2:
                    st.write(f"**Primary Contact:** {customer['ContactPerson1']}")
                    st.write(f"**Primary Email:** {customer['ContactEmail1'] or 'N/A'}")
                    st.write(f"**Primary Phone:** {customer['ContactPhone1'] or 'N/A'}")
                    if customer['ContactPerson2']:
                        st.write(f"**Secondary Contact:** {customer['ContactPerson2']}")
                        st.write(f"**Secondary Email:** {customer['ContactEmail2'] or 'N/A'}")
                        st.write(f"**Secondary Phone:** {customer['ContactPhone2'] or 'N/A'}")
                    st.write(f"**Assigned to:** {customer['assigned_name']}")
                    st.write(f"**Group:** {customer['GroupName'] or 'N/A'}")
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                
                # Status update
                current_status = customer['status']
                can_edit = (st.session_state.user['role'] == 'admin' or 
                          customer['assigned_to'] == st.session_state.user['id'])
                
                with col1:
                    if can_edit:
                        status_options = ['Chưa bắt đầu', 'Đang triển khai', 'Hoàn thành', 'Hủy bỏ']
                        new_status = st.selectbox(
                            "Status",
                            status_options,
                            index=status_options.index(current_status) if current_status in status_options else 0,
                            key=f"status_{customer['CustomerID']}"
                        )
                        
                        if new_status != current_status:
                            update_customer_status(customer['CustomerID'], new_status)
                            st.success(f"Status updated to {new_status}")
                            st.rerun()
                    else:
                        st.write(f"**Status:** {current_status}")
                
                with col2:
                    # Edit button (placeholder for future implementation)
                    if can_edit:
                        if st.button("Edit", key=f"edit_{customer['CustomerID']}", disabled=True):
                            st.info("Edit functionality coming soon!")
                
                with col3:
                    # Delete button (admin only)
                    if st.session_state.user['role'] == 'admin':
                        if st.button("Delete", key=f"delete_{customer['CustomerID']}", type="secondary"):
                            # Confirmation dialog using session state
                            st.session_state[f"confirm_delete_{customer['CustomerID']}"] = True
                        
                        # Show confirmation if delete was clicked
                        if st.session_state.get(f"confirm_delete_{customer['CustomerID']}", False):
                            st.warning(f"Are you sure you want to delete {customer['CompanyName']}? This will also delete all related services, tasks, documents, and payments.")
                            
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("Yes, Delete", key=f"confirm_yes_{customer['CustomerID']}", type="primary"):
                                    success, message = delete_customer(customer['CustomerID'])
                                    if success:
                                        st.success(message)
                                        # Clear confirmation state
                                        if f"confirm_delete_{customer['CustomerID']}" in st.session_state:
                                            del st.session_state[f"confirm_delete_{customer['CustomerID']}"]
                                        st.rerun()
                                    else:
                                        st.error(message)
                            
                            with col_no:
                                if st.button("Cancel", key=f"confirm_no_{customer['CustomerID']}"):
                                    # Clear confirmation state
                                    if f"confirm_delete_{customer['CustomerID']}" in st.session_state:
                                        del st.session_state[f"confirm_delete_{customer['CustomerID']}"]
                                    st.rerun()
    else:
        st.info("No customers found. Add your first customer above!")

# Modified show_user_management function with delete functionality
def show_user_management():
    st.header("User Management")
    
    # Add new user
    with st.expander("Add New User"):
        with st.form("add_user"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Full Name*")
                email = st.text_input("Email*")
            
            with col2:
                role = st.selectbox("Role", ['employee', 'admin'])
                password = st.text_input("Password*", type="password")
            
            submit_user = st.form_submit_button("Add User")
            
            if submit_user:
                if not name or not email or not password:
                    st.error("All fields are required!")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters long!")
                else:
                    success = add_user(email, password, role, name)
                    if success:
                        st.success("User added successfully!")
                        
                        # Send welcome email
                        subject = "Welcome to CRM System"
                        body = f"""
                        Hello {name},

                        Welcome to the CRM System! Your account has been created with the following details:

                        Email: {email}
                        Role: {role.title()}
                        Temporary Password: {password}

                        Please log in and change your password as soon as possible.

                        Best regards,
                        CRM Admin Team
                        """
                        
                        success_email, message = send_email(email, subject, body)
                        if success_email:
                            st.success("Welcome email sent successfully!")
                        else:
                            st.warning(f"User created but email failed: {message}")
                        
                        st.rerun()
                    else:
                        st.error("Failed to add user. Email might already exist.")
    
    # Display users
    st.subheader("User List")
    users_df = get_all_users()
    
    if len(users_df) > 0:
        for idx, user in users_df.iterrows():
            with st.expander(f"{user['name']} ({user['email']}) - {user['role'].title()}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Name:** {user['name']}")
                    st.write(f"**Email:** {user['email']}")
                    st.write(f"**Role:** {user['role'].title()}")
                
                with col2:
                    # Get user's assigned customers count
                    conn = sqlite3.connect('crm_database.db')
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM customers WHERE assigned_to = ?', (user['id'],))
                    customer_count = cursor.fetchone()[0]
                    conn.close()
                    
                    st.write(f"**Assigned Customers:** {customer_count}")
                    
                    # Edit button (placeholder)
                    if st.button("Edit", key=f"edit_user_{user['id']}", disabled=True):
                        st.info("Edit functionality coming soon!")
                
                with col3:
                    # Delete button (can't delete yourself)
                    if user['id'] != st.session_state.user['id']:
                        if st.button("Delete", key=f"delete_user_{user['id']}", type="secondary"):
                            st.session_state[f"confirm_delete_user_{user['id']}"] = True
                        
                        # Show confirmation if delete was clicked
                        if st.session_state.get(f"confirm_delete_user_{user['id']}", False):
                            st.warning(f"Are you sure you want to delete {user['name']}? Their assigned customers will become unassigned.")
                            
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("Yes, Delete", key=f"confirm_user_yes_{user['id']}", type="primary"):
                                    success, message = delete_user(user['id'])
                                    if success:
                                        st.success(message)
                                        # Clear confirmation state
                                        if f"confirm_delete_user_{user['id']}" in st.session_state:
                                            del st.session_state[f"confirm_delete_user_{user['id']}"]
                                        st.rerun()
                                    else:
                                        st.error(message)
                            
                            with col_no:
                                if st.button("Cancel", key=f"confirm_user_no_{user['id']}"):
                                    # Clear confirmation state
                                    if f"confirm_delete_user_{user['id']}" in st.session_state:
                                        del st.session_state[f"confirm_delete_user_{user['id']}"]
                                    st.rerun()
                    else:
                        st.info("Cannot delete yourself")
    else:
        st.info("No users found.")

# Main dashboard
def main_dashboard():
    st.title(f"Welcome, {st.session_state.user['name']}")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    if st.sidebar.button("Dashboard"):
        st.session_state.page = 'dashboard'
    if st.sidebar.button("Customers"):
        st.session_state.page = 'customers'
    if st.sidebar.button("Services"):
        st.session_state.page = 'services'
    if st.sidebar.button("Work Progress"):
        st.session_state.page = 'work_progress'
    if st.sidebar.button("Documents"):
        st.session_state.page = 'documents'
    if st.sidebar.button("Payments"):
        st.session_state.page = 'payments'
    
    unread_count = get_unread_count(st.session_state.user['id'], st.session_state.user['role'])
    notification_label = f"Notifications ({unread_count})" if unread_count > 0 else "Notifications"
    
    if st.sidebar.button(notification_label):
        st.session_state.page = 'notifications'
    
    if st.session_state.user['role'] == 'admin':
        if st.sidebar.button("User Management"):
            st.session_state.page = 'users'
        if st.sidebar.button("Approvals"):
            st.session_state.page = 'approvals'
    
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.session_state.page = 'login'
        st.rerun()
    
    # Main content
    if st.session_state.page == 'dashboard':
        show_dashboard()
    elif st.session_state.page == 'customers':
        show_customers()
    elif st.session_state.page == 'services':
        show_services()
    elif st.session_state.page == 'work_progress':
        show_work_progress()
    elif st.session_state.page == 'documents':
        show_documents()
    elif st.session_state.page == 'payments':
        show_payments()
    elif st.session_state.page == 'notifications':
        show_notifications()
    elif st.session_state.page == 'users' and st.session_state.user['role'] == 'admin':
        show_user_management()
    elif st.session_state.page == 'approvals' and st.session_state.user['role'] == 'admin':
        show_approvals()

def show_dashboard():
    st.header("Dashboard Overview")
    
    # Get dashboard statistics
    stats = get_dashboard_stats()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
    services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
    work_df = get_work_progress(st.session_state.user['id'], st.session_state.user['role'])
    
    with col1:
        st.metric("Total Customers", len(customers_df))
    with col2:
        st.metric("Active Services", len(services_df))
    with col3:
        active_tasks = len(work_df[work_df['Status'] != 'Hoàn thành'])
        st.metric("Active Tasks", active_tasks)
    with col4:
        completed_tasks = len(work_df[work_df['Status'] == 'Hoàn thành'])
        st.metric("Completed Tasks", completed_tasks)
    
    # Task status overview
    st.subheader("Task Status Overview")
    if stats['task_stats']:
        task_df = pd.DataFrame(stats['task_stats'], columns=['Status', 'Count'])
        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(task_df.set_index('Status'))
        with col2:
            st.dataframe(task_df, use_container_width=True)
    else:
        st.info("No task data available yet")
    
    # Customer progress
    st.subheader("Customer Progress Summary")
    if stats['customer_progress']:
        progress_data = []
        for customer_id, company_name, total_tasks, completed_tasks in stats['customer_progress']:
            completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            progress_data.append({
                'Customer': company_name,
                'Total Tasks': total_tasks,
                'Completed': completed_tasks,
                'Completion %': f"{completion_rate:.1f}%"
            })
        st.dataframe(pd.DataFrame(progress_data), use_container_width=True)
    else:
        st.info("No customer progress data available")
    
    # Overdue tasks warning
    if stats['overdue_tasks']:
        st.subheader("⚠️ Overdue Tasks")
        overdue_data = []
        for task_id, task_name, status, last_updated in stats['overdue_tasks']:
            overdue_data.append({
                'Task ID': task_id,
                'Task Name': task_name,
                'Status': status,
                'Last Updated': last_updated
            })
        st.dataframe(pd.DataFrame(overdue_data), use_container_width=True)

def show_services():
    st.header("Service Management")
    
    # Add new service
    with st.expander("Add New Service"):
        with st.form("add_service"):
            # Get customers for service assignment
            customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
            
            if len(customers_df) > 0:
                customer_id = st.selectbox("Customer", 
                                         options=customers_df['CustomerID'].tolist(),
                                         format_func=lambda x: f"{x} - {customers_df[customers_df['CustomerID']==x]['CompanyName'].iloc[0]}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    service_type = st.text_input("Service Type*")
                    start_date = st.date_input("Start Date")
                    package_code = st.text_input("Package Code")
                
                with col2:
                    expected_end_date = st.date_input("Expected End Date")
                    partner = st.text_input("Partner Company")
                
                description = st.text_area("Service Description")
                
                submit_service = st.form_submit_button("Add Service")
                
                if submit_service:
                    if not service_type:
                        st.error("Service Type is required!")
                    else:
                        service_id = add_service(customer_id, service_type, description, 
                                               start_date, expected_end_date, package_code, partner)
                        st.success(f"Service added successfully! ID: {service_id}")
                        st.rerun()
            else:
                st.warning("No customers available. Add customers first.")
    
    # Display services
    st.subheader("Service List")
    
    services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(services_df) > 0:
        for idx, service in services_df.iterrows():
            with st.expander(f"{service['ServiceID']} - {service['ServiceType']} ({service['CompanyName']})"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Customer:** {service['CompanyName']}")
                    st.write(f"**Service Type:** {service['ServiceType']}")
                    st.write(f"**Status:** {service['Status']}")
                    st.write(f"**Package Code:** {service['PackageCode'] or 'N/A'}")
                
                with col2:
                    st.write(f"**Start Date:** {service['StartDate']}")
                    st.write(f"**Expected End Date:** {service['ExpectedEndDate']}")
                    st.write(f"**Partner:** {service['Partner'] or 'N/A'}")
                    st.write(f"**Assigned to:** {service['assigned_name']}")
                
                if service['Description']:
                    st.write(f"**Description:** {service['Description']}")
                
                # Service actions
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("View Tasks", key=f"tasks_{service['ServiceID']}"):
                        st.session_state.selected_service = service['ServiceID']
                        st.session_state.page = 'work_progress'
                        st.rerun()
                
                with col2:
                    if st.button("View Payments", key=f"payments_{service['ServiceID']}"):
                        st.session_state.selected_service = service['ServiceID']
                        st.session_state.page = 'payments'
                        st.rerun()
                
                with col3:
                    if st.button("Add Task", key=f"add_task_{service['ServiceID']}"):
                        st.session_state.selected_service_for_task = service['ServiceID']
    else:
        st.info("No services found. Add your first service above!")

def show_work_progress():
    st.header("Work Progress & Tasks")
    
    # Add new task
    with st.expander("Add New Task"):
        with st.form("add_task"):
            # Get services for task assignment
            services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
            
            if len(services_df) > 0:
                # Pre-select service if coming from services page
                default_service = None
                if 'selected_service_for_task' in st.session_state:
                    default_service = st.session_state.selected_service_for_task
                    del st.session_state.selected_service_for_task
                
                service_options = services_df['ServiceID'].tolist()
                default_index = 0
                if default_service and default_service in service_options:
                    default_index = service_options.index(default_service)
                
                service_id = st.selectbox("Service", 
                                        options=service_options,
                                        index=default_index,
                                        format_func=lambda x: f"{x} - {services_df[services_df['ServiceID']==x]['ServiceType'].iloc[0]} ({services_df[services_df['ServiceID']==x]['CompanyName'].iloc[0]})")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    task_name = st.text_input("Task Name*")
                    start_date = st.date_input("Start Date")
                
                with col2:
                    expected_end_date = st.date_input("Expected End Date")
                
                task_description = st.text_area("Task Description")
                
                submit_task = st.form_submit_button("Add Task")
                
                if submit_task:
                    if not task_name:
                        st.error("Task Name is required!")
                    else:
                        task_id = add_work_task(service_id, task_name, task_description, 
                                              start_date, expected_end_date, st.session_state.user['id'])
                        st.success(f"Task added successfully! ID: {task_id}")
                        st.rerun()
            else:
                st.warning("No services available. Add services first.")
    
    # Display tasks
    st.subheader("Task List")
    
    work_df = get_work_progress(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(work_df) > 0:
        # Filter by status
        status_filter = st.selectbox("Filter by Status", ['All', 'Chưa bắt đầu', 'Đang thực hiện', 'Chờ duyệt', 'Hoàn thành'])
        
        if status_filter != 'All':
            filtered_df = work_df[work_df['Status'] == status_filter]
        else:
            filtered_df = work_df
        
        for idx, task in filtered_df.iterrows():
            with st.expander(f"{task['TaskID']} - {task['TaskName']} ({task['CompanyName']})"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Service:** {task['ServiceType']}")
                    st.write(f"**Customer:** {task['CompanyName']}")
                    st.write(f"**Start Date:** {task['StartDate']}")
                    st.write(f"**Expected End Date:** {task['ExpectedEndDate']}")
                
                with col2:
                    st.write(f"**Status:** {task['Status']}")
                    st.write(f"**Progress:** {task['Progress']}%")
                    st.write(f"**Last Updated:** {task['LastUpdated']}")
                    st.write(f"**Updated By:** {task['updated_by_name']}")
                
                if task['TaskDescription']:
                    st.write(f"**Description:** {task['TaskDescription']}")
                
                if task['Notes']:
                    st.write(f"**Notes:** {task['Notes']}")
                
                # Task update form
                can_edit = (st.session_state.user['role'] == 'admin' or 
                          task['updated_by_name'] == st.session_state.user['name'])
                
                if can_edit:
                    with st.form(f"update_task_{task['TaskID']}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            new_status = st.selectbox("Update Status", 
                                                    ['Chưa bắt đầu', 'Đang thực hiện', 'Chờ duyệt', 'Hoàn thành'],
                                                    index=['Chưa bắt đầu', 'Đang thực hiện', 'Chờ duyệt', 'Hoàn thành'].index(task['Status']))
                        
                        with col2:
                            new_progress = st.number_input("Progress %", min_value=0, max_value=100, value=task['Progress'])
                        
                        with col3:
                            st.write(" ")  # Spacing
                        
                        update_notes = st.text_area("Update Notes", key=f"notes_{task['TaskID']}")
                        
                        if st.form_submit_button("Update Task"):
                            update_task_status(task['TaskID'], new_status, new_progress, 
                                             st.session_state.user['id'], update_notes)
                            st.success("Task updated successfully!")
                            st.rerun()
    else:
        st.info("No tasks found. Add your first task above!")

def show_payments():
    st.header("Payment Management")
    
    # Add new payment
    with st.expander("Add New Payment"):
        with st.form("add_payment"):
            # Get services for payment assignment
            services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
            
            if len(services_df) > 0:
                service_id = st.selectbox("Service", 
                                        options=services_df['ServiceID'].tolist(),
                                        format_func=lambda x: f"{x} - {services_df[services_df['ServiceID']==x]['ServiceType'].iloc[0]} ({services_df[services_df['ServiceID']==x]['CompanyName'].iloc[0]})")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    currency = st.selectbox("Currency", ['VND', 'USD', 'EUR', 'SGD', 'HKD', 'JPY'])
                    original_amount = st.number_input("Original Amount", min_value=0.0, format="%.2f")
                
                with col2:
                    exchange_rate = st.number_input("Exchange Rate (if applicable)", min_value=0.0, value=1.0, format="%.4f")
                    deposit_amount = st.number_input("Deposit Amount", min_value=0.0, format="%.2f")
                
                notes = st.text_area("Payment Notes")
                
                submit_payment = st.form_submit_button("Add Payment")
                
                if submit_payment:
                    if original_amount <= 0:
                        st.error("Original Amount must be greater than 0!")
                    else:
                        payment_id = add_payment(service_id, currency, original_amount, 
                                               exchange_rate, deposit_amount, notes)
                        st.success(f"Payment record added successfully! ID: {payment_id}")
                        st.rerun()
            else:
                st.warning("No services available. Add services first.")
    
    # Display payments
    st.subheader("Payment List")
    
    services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(services_df) > 0:
        for _, service in services_df.iterrows():
            payments_df = get_payments_by_service(service['ServiceID'])
            
            if len(payments_df) > 0:
                st.write(f"**{service['ServiceID']} - {service['ServiceType']} ({service['CompanyName']})**")
                
                for _, payment in payments_df.iterrows():
                    with st.expander(f"Payment {payment['PaymentID']} - {payment['Currency']} {payment['OriginalAmount']:,.2f}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Currency:** {payment['Currency']}")
                            st.write(f"**Original Amount:** {payment['OriginalAmount']:,.2f}")
                            st.write(f"**Exchange Rate:** {payment['ExchangeRate']}")
                            st.write(f"**Converted Amount:** {payment['ConvertedAmount']:,.2f}")
                        
                        with col2:
                            total_paid = (payment['DepositAmount'] or 0) + (payment['FirstPaymentAmount'] or 0) + (payment['SecondPaymentAmount'] or 0)
                            payment_status = 'Đầy đủ' if total_paid >= payment['ConvertedAmount'] else 'Chưa đủ'
                            
                            st.write(f"**Deposit:** {payment['DepositAmount'] or 0:,.2f}")
                            st.write(f"**First Payment:** {payment['FirstPaymentAmount'] or 0:,.2f}")
                            st.write(f"**Second Payment:** {payment['SecondPaymentAmount'] or 0:,.2f}")
                            st.write(f"**Total Paid:** {total_paid:,.2f}")
                            st.write(f"**Status:** {payment_status}")
                        
                        if payment['Notes']:
                            st.write(f"**Notes:** {payment['Notes']}")
                        
                        # Payment update form
                        with st.form(f"update_payment_{payment['PaymentID']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                first_payment = st.number_input("First Payment Amount", 
                                                               min_value=0.0, 
                                                               value=float(payment['FirstPaymentAmount'] or 0),
                                                               format="%.2f",
                                                               key=f"first_{payment['PaymentID']}")
                                first_date = st.date_input("First Payment Date", 
                                                         value=pd.to_datetime(payment['FirstPaymentDate']).date() if payment['FirstPaymentDate'] else None,
                                                         key=f"first_date_{payment['PaymentID']}")
                            
                            with col2:
                                second_payment = st.number_input("Second Payment Amount", 
                                                                min_value=0.0, 
                                                                value=float(payment['SecondPaymentAmount'] or 0),
                                                                format="%.2f",
                                                                key=f"second_{payment['PaymentID']}")
                                second_date = st.date_input("Second Payment Date", 
                                                          value=pd.to_datetime(payment['SecondPaymentDate']).date() if payment['SecondPaymentDate'] else None,
                                                          key=f"second_date_{payment['PaymentID']}")
                            
                            if st.form_submit_button("Update Payment"):
                                update_payment(payment['PaymentID'], first_payment, first_date, 
                                             second_payment, second_date)
                                st.success("Payment updated successfully!")
                                st.rerun()
                
                st.divider()
    else:
        st.info("No services with payments found.")

def show_documents():
    st.header("Document Management")
    
    # Add new document
    with st.expander("Add New Document"):
        with st.form("add_document"):
            # Get customers and services
            customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
            
            if len(customers_df) > 0:
                customer_id = st.selectbox("Customer", 
                                         options=customers_df['CustomerID'].tolist(),
                                         format_func=lambda x: f"{x} - {customers_df[customers_df['CustomerID']==x]['CompanyName'].iloc[0]}")
                
                # Get services for selected customer
                services_df = get_services_by_customer(customer_id)
                service_id = None
                if len(services_df) > 0:
                    service_id = st.selectbox("Service (Optional)", 
                                            options=[''] + services_df['ServiceID'].tolist(),
                                            format_func=lambda x: f"{x} - {services_df[services_df['ServiceID']==x]['ServiceType'].iloc[0]}" if x else "No Service")
                    if service_id == '':
                        service_id = None
                
                col1, col2 = st.columns(2)
                
                with col1:
                    document_type = st.selectbox("Document Type", 
                                               ['NDA', 'Invoice', 'Payment Receipt', 'Contract', 'Proposal', 'Report', 'Other'])
                    document_name = st.text_input("Document Name*")
                
                with col2:
                    # Get users for responsible person
                    users_df = get_all_users()
                    responsible_person = st.selectbox("Responsible Person", 
                                                    options=users_df['id'].tolist(),
                                                    format_func=lambda x: users_df[users_df['id']==x]['name'].iloc[0])
                
                notes = st.text_area("Document Notes")
                
                submit_document = st.form_submit_button("Add Document")
                
                if submit_document:
                    if not document_name:
                        st.error("Document Name is required!")
                    else:
                        doc_id = add_document(customer_id, service_id, document_type, 
                                            document_name, responsible_person, notes)
                        st.success(f"Document added successfully! ID: {doc_id}")
                        st.rerun()
            else:
                st.warning("No customers available. Add customers first.")
    
    # Display documents
    st.subheader("Document List")
    
    documents_df = get_documents(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(documents_df) > 0:
        # Filter by document type
        doc_types = ['All'] + list(documents_df['DocumentType'].unique())
        type_filter = st.selectbox("Filter by Type", doc_types)
        
        if type_filter != 'All':
            filtered_df = documents_df[documents_df['DocumentType'] == type_filter]
        else:
            filtered_df = documents_df
        
        for idx, doc in filtered_df.iterrows():
            with st.expander(f"{doc['DocumentID']} - {doc['DocumentName']} ({doc['CompanyName']})"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Customer:** {doc['CompanyName']}")
                    st.write(f"**Service:** {doc['ServiceType'] or 'N/A'}")
                    st.write(f"**Document Type:** {doc['DocumentType']}")
                    st.write(f"**Status:** {doc['Status']}")
                
                with col2:
                    st.write(f"**Created Date:** {doc['CreatedDate']}")
                    st.write(f"**Responsible Person:** {doc['responsible_name']}")
                
                if doc['Notes']:
                    st.write(f"**Notes:** {doc['Notes']}")
                
                # Status update
                can_edit = (st.session_state.user['role'] == 'admin' or 
                          doc['responsible_name'] == st.session_state.user['name'])
                
                if can_edit:
                    status_options = ['Đang xử lý', 'Đã ký', 'Đã gửi', 'Đã nhận', 'Hủy bỏ']
                    new_status =new_status = st.selectbox("Update Status", 
                                             status_options,
                                             index=status_options.index(doc['Status']) if doc['Status'] in status_options else 0,
                                             key=f"doc_status_{doc['DocumentID']}")
                    
                    if st.button(f"Update Status", key=f"update_doc_{doc['DocumentID']}"):
                        update_document_status(doc['DocumentID'], new_status)
                        st.success(f"Document status updated to {new_status}")
                        st.rerun()
    else:
        st.info("No documents found. Add your first document above!")

def show_notifications():
    st.header("Notifications")
    
    notifications_df = get_notifications(st.session_state.user['id'], st.session_state.user['role'])
    
    if len(notifications_df) > 0:
        st.subheader("Recent Notifications")
        
        for idx, notification in notifications_df.iterrows():
            if not notification['read']:
                st.markdown(f"**🔴 {notification['message']}**")
                st.caption(f"Created: {notification['created_at']}")
                
                if st.button(f"Mark as Read", key=f"read_{notification['id']}"):
                    mark_notification_read(notification['id'])
                    st.rerun()
            else:
                st.markdown(f"✅ {notification['message']}")
                st.caption(f"Created: {notification['created_at']}")
            
            st.divider()
    else:
        st.info("No notifications found.")


def show_approvals():
    st.header("Customer Approvals")
    
    pending_customers = get_pending_customers()
    
    if len(pending_customers) > 0:
        st.subheader("Pending Customer Approvals")
        
        for idx, customer in pending_customers.iterrows():
            with st.expander(f"PENDING: {customer['CustomerID']} - {customer['CompanyName']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Company Name:** {customer['CompanyName']}")
                    st.write(f"**Tax Code:** {customer['TaxCode'] or 'N/A'}")
                    st.write(f"**Address:** {customer['Address'] or 'N/A'}")
                    st.write(f"**Country:** {customer['Country']}")
                    st.write(f"**Category:** {customer['CustomerCategory']} - {customer['CustomerType']}")
                
                with col2:
                    st.write(f"**Primary Contact:** {customer['ContactPerson1']}")
                    st.write(f"**Primary Email:** {customer['ContactEmail1'] or 'N/A'}")
                    st.write(f"**Primary Phone:** {customer['ContactPhone1'] or 'N/A'}")
                    st.write(f"**Industry:** {customer['Industry'] or 'N/A'}")
                    st.write(f"**Source:** {customer['Source'] or 'N/A'}")
                    st.write(f"**Assigned to:** {customer['assigned_name']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Approve", key=f"approve_{customer['CustomerID']}", type="primary"):
                        approve_customer(customer['CustomerID'])
                        
                        # Send approval email to assigned employee
                        if customer['ContactEmail1']:
                            subject = f"Customer Approved: {customer['CompanyName']}"
                            body = f"""
                            Hello,

                            The customer '{customer['CompanyName']}' (ID: {customer['CustomerID']}) has been approved and is now active in the system.

                            You can now begin working with this customer and managing their services.

                            Customer Details:
                            - Company: {customer['CompanyName']}
                            - Contact: {customer['ContactPerson1']}
                            - Email: {customer['ContactEmail1']}
                            - Phone: {customer['ContactPhone1']}

                            Best regards,
                            CRM System
                            """
                            send_email(customer['ContactEmail1'], subject, body)
                        
                        st.success(f"Customer {customer['CompanyName']} approved!")
                        st.rerun()
                
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{customer['CustomerID']}"):
                        # You might want to implement a rejection function
                        # For now, we'll just delete the customer
                        conn = sqlite3.connect('crm_database.db')
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM customers WHERE CustomerID = ?', (customer['CustomerID'],))
                        conn.commit()
                        conn.close()
                        
                        st.success(f"Customer {customer['CompanyName']} rejected and removed!")
                        st.rerun()
    else:
        st.info("No customers pending approval.")

# Add some utility functions for reporting
def show_reports():
    st.header("Reports & Analytics")
    
    # Basic statistics
    st.subheader("System Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
    services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
    work_df = get_work_progress(st.session_state.user['id'], st.session_state.user['role'])
    documents_df = get_documents(st.session_state.user['id'], st.session_state.user['role'])
    
    with col1:
        st.metric("Total Customers", len(customers_df))
    with col2:
        st.metric("Active Services", len(services_df))
    with col3:
        st.metric("Total Tasks", len(work_df))
    with col4:
        st.metric("Total Documents", len(documents_df))
    
    # Customer distribution by country
    if len(customers_df) > 0:
        st.subheader("Customer Distribution by Country")
        country_counts = customers_df['Country'].value_counts()
        st.bar_chart(country_counts)
        
        # Customer category breakdown
        st.subheader("Customer Category Breakdown")
        category_counts = customers_df['CustomerCategory'].value_counts()
        category_labels = {'I': 'Individual', 'H': 'Household Business', 'C': 'Company'}
        category_counts.index = [category_labels.get(x, x) for x in category_counts.index]
        st.bar_chart(category_counts)
    
    # Task completion rates
    if len(work_df) > 0:
        st.subheader("Task Status Distribution")
        status_counts = work_df['Status'].value_counts()
        st.bar_chart(status_counts)
        
        # Progress overview
        st.subheader("Task Progress Overview")
        avg_progress = work_df['Progress'].mean()
        st.metric("Average Task Progress", f"{avg_progress:.1f}%")
        
        # Progress histogram
        st.bar_chart(work_df['Progress'].value_counts().sort_index())

def export_data():
    st.header("Data Export")
    
    export_options = st.multiselect(
        "Select data to export:",
        ["Customers", "Services", "Work Progress", "Documents", "Payments"],
        default=["Customers"]
    )
    
    if st.button("Generate Export"):
        export_data = {}
        
        if "Customers" in export_options:
            customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
            export_data['customers'] = customers_df
        
        if "Services" in export_options:
            services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
            export_data['services'] = services_df
        
        if "Work Progress" in export_options:
            work_df = get_work_progress(st.session_state.user['id'], st.session_state.user['role'])
            export_data['work_progress'] = work_df
        
        if "Documents" in export_options:
            documents_df = get_documents(st.session_state.user['id'], st.session_state.user['role'])
            export_data['documents'] = documents_df
        
        # Display export data
        for key, df in export_data.items():
            st.subheader(f"{key.title()} Data")
            st.dataframe(df, use_container_width=True)
            
            # Convert to CSV for download
            csv = df.to_csv(index=False)
            st.download_button(
                label=f"Download {key.title()} CSV",
                data=csv,
                file_name=f"{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

# Main application logic
def main():
    st.set_page_config(
        page_title="CRM System",
        page_icon="📊",
        layout="wide"
    )
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .stButton > button {
        width: 100%;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if st.session_state.user is None:
        login_page()
    else:
        main_dashboard()

if __name__ == "__main__":
    main()

# Add these functions to your existing code

def delete_customer(customer_id):
    """Delete a customer and all related data"""
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    try:
        # Start transaction
        cursor.execute('BEGIN TRANSACTION')
        
        # Delete in order of dependencies (foreign key constraints)
        # 1. Delete work_progress related to this customer's services
        cursor.execute('''
            DELETE FROM work_progress 
            WHERE ServiceID IN (
                SELECT ServiceID FROM services WHERE CustomerID = ?
            )
        ''', (customer_id,))
        
        # 2. Delete work_billing related to this customer's services
        cursor.execute('''
            DELETE FROM work_billing 
            WHERE ServiceID IN (
                SELECT ServiceID FROM services WHERE CustomerID = ?
            )
        ''', (customer_id,))
        
        # 3. Delete payments related to this customer's services
        cursor.execute('''
            DELETE FROM payments 
            WHERE ServiceID IN (
                SELECT ServiceID FROM services WHERE CustomerID = ?
            )
        ''', (customer_id,))
        
        # 4. Delete documents related to this customer
        cursor.execute('DELETE FROM client_documents WHERE CustomerID = ?', (customer_id,))
        
        # 5. Delete services related to this customer
        cursor.execute('DELETE FROM services WHERE CustomerID = ?', (customer_id,))
        
        # 6. Delete notifications related to this customer
        cursor.execute('DELETE FROM notifications WHERE related_id = ?', (customer_id,))
        
        # 7. Finally delete the customer
        cursor.execute('DELETE FROM customers WHERE CustomerID = ?', (customer_id,))
        
        # Commit transaction
        cursor.execute('COMMIT')
        
        conn.close()
        return True, "Customer deleted successfully"
        
    except sqlite3.Error as e:
        cursor.execute('ROLLBACK')
        conn.close()
        return False, f"Error deleting customer: {str(e)}"

def delete_user(user_id):
    """Delete a user and handle reassignment of their data"""
    conn = sqlite3.connect('crm_database.db')
    cursor = conn.cursor()
    
    try:
        # Check if user is the last admin
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        admin_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
        user_role = cursor.fetchone()
        
        if user_role and user_role[0] == 'admin' and admin_count <= 1:
            return False, "Cannot delete the last admin user"
        
        # Start transaction
        cursor.execute('BEGIN TRANSACTION')
        
        # Set assigned customers to unassigned (NULL)
        cursor.execute('UPDATE customers SET assigned_to = NULL WHERE assigned_to = ?', (user_id,))
        
        # Set work progress UpdatedBy to NULL where applicable
        cursor.execute('UPDATE work_progress SET UpdatedBy = NULL WHERE UpdatedBy = ?', (user_id,))
        
        # Set document responsible person to NULL
        cursor.execute('UPDATE client_documents SET ResponsiblePerson = NULL WHERE ResponsiblePerson = ?', (user_id,))
        
        # Delete user's notifications
        cursor.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
        
        # Finally delete the user
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        
        # Commit transaction
        cursor.execute('COMMIT')
        
        conn.close()
        return True, "User deleted successfully"
        
    except sqlite3.Error as e:
        cursor.execute('ROLLBACK')
        conn.close()
        return False, f"Error deleting user: {str(e)}"

