import streamlit as st
import bcrypt
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pymssql
import sqlite3

def get_auth_connection():
    return sqlite3.connect("auth.db")

def init_auth_database():
    conn = get_auth_connection()
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

    # Customer Groups
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_groups (
            GroupID TEXT PRIMARY KEY,
            GroupName TEXT NOT NULL,
            Description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_meta (
            CustomerID TEXT PRIMARY KEY,
            assigned_to TEXT,
            status TEXT DEFAULT 'Chưa bắt đầu',
            approved INTEGER DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # Notifications
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

    # Ensure default admin user
    cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cursor.fetchone()[0] == 0:
        admin_id = str(uuid.uuid4())
        password = "admin123"
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            "INSERT INTO users (id, email, password_hash, role, name) VALUES (?, ?, ?, ?, ?)",
            (admin_id, "admin@company.com", hashed, "admin", "Admin User")
        )

    conn.commit()
    conn.close()
    print("SQLite auth.db initialized ✅")

def get_connection():
    """Create and return a SQL Server connection."""
    return pymssql.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=14.224.227.37,1434;"   # <-- change this
        "DATABASE=SlinerNB;"                # <-- change this
        "UID=SlinerOwner;"              # <-- SQL Auth user (remove if Windows auth)
        "PWD=Sliner!19870310;"              # <-- SQL Auth password
    )

def get_crm_connection():
    """Get connection to CRM database (SQL Server)"""
    return get_connection()  # Uses your existing SQL Server connection

def init_database():
    """
    Initialize database connection.
    Unlike SQLite, we don't create tables here — 
    assume schema already exists in SQL Server.
    Just ensure defaults (admin user, groups, etc.).
    """
    max_retries = 2
    
    for attempt in range(max_retries):
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # ---- Ensure default admin user exists ----
            cursor.execute("SELECT COUNT(*) FROM Users WHERE role = 'admin'")
            admin_count = cursor.fetchone()[0]

            if admin_count == 0:
                admin_id = str(uuid.uuid4())
                password = "admin123"
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

                cursor.execute('''
                    INSERT INTO Users (id, email, password_hash, role, name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (admin_id, "admin@company.com", hashed_password.decode('utf-8'), "admin", "Admin User"))
                print("Default admin user created (email: admin@company.com / password: admin123)")

            # ---- Ensure default customer groups exist ----
            cursor.execute("SELECT COUNT(*) FROM Customer_Groups")
            group_count = cursor.fetchone()[0]

            if group_count == 0:
                sample_groups = [
                    ('GRP001', 'VIP Customers', 'High priority customers'),
                    ('GRP002', 'Regular Customers', 'Standard customers'),
                    ('GRP003', 'New Leads', 'Potential customers')
                ]
                cursor.executemany('''
                    INSERT INTO Customer_Groups (GroupID, GroupName, Description)
                    VALUES (?, ?, ?)
                ''', sample_groups)
                print("Default customer groups inserted")

            conn.commit()
            conn.close()
            print("Database initialized successfully!")
            return True

        except Exception as e:
            print(f"Database connection/init error on attempt {attempt + 1}: {e}")

            try:
                conn.close()
            except:
                pass

            if attempt < max_retries - 1:
                print("Retrying connection...")
            else:
                print("Failed to initialize database after all attempts")
                return False
    
    return False
    
    return False

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    # make sure hashed is in bytes
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def authenticate_user(email, password):
    conn = get_auth_connection()  # <-- use SQLite
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, role, name FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(password, user[1]):
        return {'id': user[0], 'email': email, 'role': user[2], 'name': user[3]}
    return None

def generate_customer_id(country, category):
    conn = get_connection()  # Your SQL Server connection
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
        SELECT MAX(CAST(SUBSTRING(CustomerID, 5, 6) AS INT)) 
        FROM CRM_Customers 
        WHERE SUBSTRING(CustomerID, 1, 4) = ?
    ''', (prefix,))
    
    result = cursor.fetchone()[0]
    max_id = result if result else 0
    
    new_id = f"{prefix}{str(max_id + 1).zfill(6)}"
    conn.close()
    
    return new_id

# ---------- Users (SQLite auth.db) ----------
def get_all_users():
    conn = get_auth_connection()
    df = pd.read_sql_query('SELECT id, name, email, role FROM users', conn)
    conn.close()
    return df


def add_user(email, password, role, name):
    """
    Create user in SQLite auth.db.
    Returns True on success, False if duplicate or error.
    """
    try:
        conn = get_auth_connection()
        cursor = conn.cursor()

        user_id = str(uuid.uuid4())
        hashed_password = hash_password(password)  # bcrypt bytes
        if isinstance(hashed_password, bytes):
            hashed_password = hashed_password.decode('utf-8')  # store as text

        cursor.execute('''
            INSERT INTO users (id, email, password_hash, role, name)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, email, hashed_password, role, name))

        conn.commit()
        conn.close()
        return True

    except sqlite3.IntegrityError:
        # Unique constraint violation (duplicate email, etc.)
        return False

    except Exception as e:
        print(f"Error adding user: {e}")
        return False

# ---------- Customer groups (SQLite auth.db) ----------
def get_customer_groups():
    conn = get_auth_connection()
    df = pd.read_sql_query('SELECT * FROM customer_groups', conn)
    conn.close()
    return df

def add_customer_enhanced(company_name, tax_code, group_id, address, country, customer_category, 
                         company_type, contact_person1, contact_email1, contact_phone1,
                         contact_person2, contact_email2, contact_phone2, industry, source,
                         assigned_to, created_by, auto_approve=False):
    """
    Insert customer into SQL Server CRM_Customers table and metadata into SQLite auth.db
    """
    print(f"DEBUG: Starting add_customer_enhanced for {company_name}")
    
    # 1) Insert into SQL Server CRM_Customers (using correct columns)
    try:
        crm_conn = get_connection()
        crm_cursor = crm_conn.cursor()
        
        customer_id = generate_customer_id(country, customer_category)
        created_date = datetime.now().date()
        print(f"DEBUG: Generated customer_id: {customer_id}")

        # FIXED: Using actual CRM_Customers columns
        crm_cursor.execute('''
            INSERT INTO CRM_Customers (
                CustomerID, CompanyName, TaxCode, GroupID, Address, Country, CustomerCategory,
                CompanyType, ContactPerson1, ContactEmail1, ContactPhone1,
                ContactPerson2, ContactEmail2, ContactPhone2, Industry, Source, CreatedDate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            customer_id, company_name, tax_code, group_id, address, country, customer_category,
            company_type, contact_person1, contact_email1, contact_phone1,
            contact_person2, contact_email2, contact_phone2, industry, source, created_date
        ))
        crm_conn.commit()
        crm_conn.close()
        print("DEBUG: Successfully inserted into CRM_Customers")
        
    except Exception as e:
        print(f"ERROR: Failed to insert into CRM_Customers: {e}")
        return None

    # 2) Insert metadata into SQLite auth.db (this part stays the same)
    try:
        auth_conn = get_auth_connection()
        auth_cursor = auth_conn.cursor()

        approved_flag = 1 if auto_approve else 0
        print(f"DEBUG: About to insert into customer_meta with approved={approved_flag}")
        
        auth_cursor.execute('''
            INSERT OR REPLACE INTO customer_meta (CustomerID, assigned_to, status, approved, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (customer_id, assigned_to, 'Chưa bắt đầu', approved_flag, created_by))
        
        if not auto_approve:
            notification_id = str(uuid.uuid4())
            auth_cursor.execute('''
                INSERT INTO notifications (id, user_id, message, type, related_id, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (notification_id, None, f"New customer '{company_name}' needs approval", "customer_approval", customer_id))

        auth_conn.commit()
        auth_conn.close()
        print("DEBUG: Successfully committed all auth.db changes")
        
        return customer_id
        
    except Exception as e:
        print(f"ERROR: Failed to insert into auth.db: {e}")
        return None

def get_customers_enhanced(user_id=None, user_role=None):
    """
    Fetch customers from CRM_Customers and enrich with auth data
    """
    # Get customers from SQL Server (using correct table name)
    crm_conn = get_connection()
    try:
        crm_df = pd.read_sql_query('SELECT * FROM CRM_Customers', crm_conn)
    except Exception as e:
        print(f"Error fetching customers: {e}")
        crm_df = pd.DataFrame()
    crm_conn.close()

    if crm_df.empty:
        return crm_df

    # Get meta from SQLite auth.db
    auth_conn = get_auth_connection()
    try:
        meta_df = pd.read_sql_query('SELECT CustomerID, assigned_to, status, approved FROM customer_meta', auth_conn)
    except Exception:
        meta_df = pd.DataFrame(columns=['CustomerID','assigned_to','status','approved'])
    try:
        users_df = pd.read_sql_query('SELECT id, name FROM users', auth_conn)
    except Exception:
        users_df = pd.DataFrame(columns=['id','name'])
    try:
        groups_df = pd.read_sql_query('SELECT GroupID, GroupName FROM customer_groups', auth_conn)
    except Exception:
        groups_df = pd.DataFrame(columns=['GroupID','GroupName'])
    auth_conn.close()

    # Merge dataframes
    df = crm_df.merge(meta_df, on='CustomerID', how='left')

    # Map assigned_to -> assigned_name
    if not users_df.empty:
        users_df = users_df.rename(columns={'id': 'assigned_to', 'name': 'assigned_name'})
        df = df.merge(users_df, on='assigned_to', how='left')
    else:
        df['assigned_name'] = None

    # Map GroupID -> GroupName
    if not groups_df.empty:
        df = df.merge(groups_df, on='GroupID', how='left')
    else:
        df['GroupName'] = None

    # Normalize approved/status defaults
    df['approved'] = df['approved'].fillna(0).astype(int)
    df['status'] = df['status'].fillna('Chưa bắt đầu')

    # Filter by role
    if user_role == 'admin':
        df_filtered = df[df['approved'] == 1]
    else:
        df_filtered = df[(df['assigned_to'] == user_id) & (df['approved'] == 1)]

    return df_filtered.reset_index(drop=True)

def generate_customer_id(country, category):
    crm_conn = get_connection()
    crm_cursor = crm_conn.cursor()
    
    prefix_map = {
        'Vietnam': 'VND',
        'United States': 'USD', 
        'Singapore': 'SGD',
        'Hong Kong': 'HKD',
        'Japan': 'JPY'
    }
    
    prefix = prefix_map.get(country, 'XXX') + category
    
    # FIXED: Using correct table name CRM_Customers
    crm_cursor.execute('''
        SELECT MAX(CAST(SUBSTRING(CustomerID, 5, 6) AS INT)) 
        FROM CRM_Customers 
        WHERE SUBSTRING(CustomerID, 1, 4) = ?
    ''', (prefix,))
    
    result = crm_cursor.fetchone()[0]
    max_id = result if result else 0
    
    new_id = f"{prefix}{str(max_id + 1).zfill(6)}"
    crm_conn.close()
    
    return new_id

# ---------- Pending customers (not approved) ----------
def get_pending_customers():
    # Fetch all customers then filter using auth.customer_meta.approved = 0
    crm_conn = get_crm_connection()
    try:
        crm_df = pd.read_sql_query('SELECT * FROM CRM_Customers', crm_conn)
    except Exception:
        crm_df = pd.DataFrame()
    crm_conn.close()

    auth_conn = get_auth_connection()
    try:
        meta_df = pd.read_sql_query('SELECT CustomerID, assigned_to, status, approved FROM customer_meta', auth_conn)
    except Exception:
        meta_df = pd.DataFrame(columns=['CustomerID','assigned_to','status','approved'])
    try:
        users_df = pd.read_sql_query('SELECT id, name FROM users', auth_conn)
    except Exception:
        users_df = pd.DataFrame(columns=['id','name'])
    try:
        groups_df = pd.read_sql_query('SELECT GroupID, GroupName FROM customer_groups', auth_conn)
    except Exception:
        groups_df = pd.DataFrame(columns=['GroupID','GroupName'])
    auth_conn.close()

    if crm_df.empty:
        return crm_df

    df = crm_df.merge(meta_df, on='CustomerID', how='left')
    if not users_df.empty:
        users_df = users_df.rename(columns={'id': 'assigned_to', 'name': 'assigned_name'})
        df = df.merge(users_df, on='assigned_to', how='left')
    else:
        df['assigned_name'] = None
    if not groups_df.empty:
        df = df.merge(groups_df, on='GroupID', how='left')
    else:
        df['GroupName'] = None

    df['approved'] = df['approved'].fillna(0).astype(int)
    pending = df[df['approved'] == 0].reset_index(drop=True)
    return pending

def approve_customer(customer_id):
    """Approve customer by updating the approved flag in SQLite auth.db"""
    auth_conn = get_auth_connection()
    cursor = auth_conn.cursor()
    
    # Check if record exists in customer_meta
    cursor.execute('SELECT COUNT(*) FROM customer_meta WHERE CustomerID = ?', (customer_id,))
    exists = cursor.fetchone()[0]
    
    if exists:
        # Update existing record
        cursor.execute('UPDATE customer_meta SET approved = 1 WHERE CustomerID = ?', (customer_id,))
        print(f"Updated existing customer_meta record for {customer_id}")
    else:
        # Insert new record if it doesn't exist
        cursor.execute('''
            INSERT INTO customer_meta (CustomerID, approved, status, created_at)
            VALUES (?, 1, 'Chưa bắt đầu', CURRENT_TIMESTAMP)
        ''', (customer_id,))
        print(f"Created new customer_meta record for {customer_id}")
    
    # Clear any pending approval notifications for this customer
    cursor.execute('UPDATE notifications SET [read] = 1 WHERE related_id = ? AND type = ?', 
                  (customer_id, 'customer_approval'))
    
    auth_conn.commit()
    auth_conn.close()
    
    print(f"Customer {customer_id} approved successfully!")
    
def update_customer_status(customer_id, new_status):
    conn = get_auth_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM customer_meta WHERE CustomerID = ?', (customer_id,))
    res = cursor.fetchone()
    exists = res[0] if res else 0

    if exists:
        cursor.execute('UPDATE customer_meta SET status = ? WHERE CustomerID = ?', (new_status, customer_id))
    else:
        cursor.execute('''
            INSERT INTO customer_meta (CustomerID, status, approved, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (customer_id, new_status, 0))

    conn.commit()
    conn.close()
    return True

# ---------- Service management (SQL Server) ----------
def add_service(customer_id, service_type, description, start_date, expected_end_date, package_code, partner):
    """Add service to CRM_Services table using correct columns"""
    crm_conn = get_connection()
    crm_cursor = crm_conn.cursor()
    
    service_id = f"DV{str(uuid.uuid4())[:6].upper()}"
    
    # FIXED: Using actual CRM_Services columns
    crm_cursor.execute('''
        INSERT INTO CRM_Services (ServiceID, CustomerID, ServiceType, Description, StartDate, ExpectedEndDate, PackageCode, Partner, Status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (service_id, customer_id, service_type, description, start_date, expected_end_date, package_code, partner, 'Active'))
    
    crm_conn.commit()
    crm_conn.close()
    return service_id

def get_services_by_customer(customer_id):
    """Get services for a specific customer"""
    crm_conn = get_connection()
    try:
        df = pd.read_sql_query('SELECT * FROM CRM_Services WHERE CustomerID = ?', crm_conn, params=(customer_id,))
    except Exception:
        df = pd.DataFrame()
    crm_conn.close()
    return df


def get_all_services(user_id=None, user_role=None):
    """
    Fetch services from CRM_Services and enrich with customer data
    """
    crm_conn = get_connection()
    try:
        # FIXED: Using correct table names
        services_df = pd.read_sql_query('''
            SELECT s.*, c.CompanyName 
            FROM CRM_Services s
            JOIN CRM_Customers c ON s.CustomerID = c.CustomerID
        ''', crm_conn)
    except Exception as e:
        print(f"Error fetching services: {e}")
        services_df = pd.DataFrame()
    crm_conn.close()
    
    if services_df.empty:
        return services_df

    # Load meta from auth.db (this part is correct)
    auth_conn = get_auth_connection()
    try:
        meta_df = pd.read_sql_query('SELECT CustomerID, assigned_to, status, approved FROM customer_meta', auth_conn)
    except Exception:
        meta_df = pd.DataFrame(columns=['CustomerID','assigned_to','status','approved'])
    try:
        users_df = pd.read_sql_query('SELECT id, name FROM users', auth_conn)
    except Exception:
        users_df = pd.DataFrame(columns=['id','name'])
    auth_conn.close()

    # Merge dataframes
    df = services_df.merge(meta_df, on='CustomerID', how='left')
    if not users_df.empty:
        users_df = users_df.rename(columns={'id': 'assigned_to', 'name': 'assigned_name'})
        df = df.merge(users_df, on='assigned_to', how='left')
    else:
        df['assigned_name'] = None

    df['approved'] = df['approved'].fillna(0).astype(int)
    df['status'] = df['status'].fillna('Chưa bắt đầu')

    # Filter by role
    if user_role == 'admin':
        df_filtered = df[df['approved'] == 1]
    else:
        df_filtered = df[(df['assigned_to'] == user_id) & (df['approved'] == 1)]

    return df_filtered.reset_index(drop=True)

# ---------- Work Progress (SQL Server) ----------
def add_work_task(service_id, task_name, task_description, start_date, expected_end_date, updated_by):
    crm_conn = get_crm_connection()
    crm_cursor = crm_conn.cursor()
    
    task_id = f"CV{str(uuid.uuid4())[:6].upper()}"
    
    crm_cursor.execute('''
        INSERT INTO WorkProgress (TaskID, ServiceID, TaskName, TaskDescription, StartDate, ExpectedEndDate, UpdatedBy, LastUpdated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, service_id, task_name, task_description, start_date, expected_end_date, updated_by, datetime.now().date()))
    
    crm_conn.commit()
    crm_conn.close()
    return task_id


def get_work_progress(user_id=None, user_role=None):
    """
    Fetch work progress from SQL Server and enrich with auth.db user names and customer meta.
    """
    crm_conn = get_crm_connection()
    try:
        wp_df = pd.read_sql_query('''
            SELECT wp.*, s.ServiceType, s.CustomerID, c.CompanyName
            FROM WorkProgress wp
            JOIN Services s ON wp.ServiceID = s.ServiceID
            JOIN Customers c ON s.CustomerID = c.CustomerID
        ''', crm_conn)
    except Exception:
        wp_df = pd.DataFrame()
    crm_conn.close()
    
    if wp_df.empty:
        return wp_df

    # enrich from auth.db
    auth_conn = get_auth_connection()
    try:
        meta_df = pd.read_sql_query('SELECT CustomerID, assigned_to, approved FROM customer_meta', auth_conn)
    except Exception:
        meta_df = pd.DataFrame(columns=['CustomerID','assigned_to','approved'])
    try:
        users_df = pd.read_sql_query('SELECT id, name FROM users', auth_conn)
    except Exception:
        users_df = pd.DataFrame(columns=['id','name'])
    auth_conn.close()

    df = wp_df.merge(meta_df, on='CustomerID', how='left')

    # map updated_by id -> name
    if not users_df.empty:
        users_df = users_df.rename(columns={'id': 'UpdatedBy', 'name': 'updated_by_name'})
        df = df.merge(users_df, on='UpdatedBy', how='left')
    else:
        df['updated_by_name'] = None

    df['approved'] = df['approved'].fillna(0).astype(int)

    # Filter by role
    if user_role == 'admin':
        df_filtered = df[df['approved'] == 1]
    else:
        df_filtered = df[(df['assigned_to'] == user_id) & (df['approved'] == 1)]

    return df_filtered.reset_index(drop=True)


def update_task_status(task_id, new_status, progress, updated_by, notes=""):
    """
    Update task status in SQL Server. Use Python to set LastUpdated (safer cross-DB).
    """
    crm_conn = get_crm_connection()
    cursor = crm_conn.cursor()
    last_updated = datetime.now().date()
    cursor.execute('''
        UPDATE WorkProgress
        SET Status = ?, Progress = ?, UpdatedBy = ?, Notes = ?, LastUpdated = ?
        WHERE TaskID = ?
    ''', (new_status, progress, updated_by, notes, last_updated, task_id))
    crm_conn.commit()
    crm_conn.close()

# ---------- Invoice (SQL Server) ----------
def add_invoice(service_id, customer_id, amount_original, currency, due_date, notes=""):
    """Add invoice to CRM_Invoice table"""
    crm_conn = get_connection()
    cursor = crm_conn.cursor()
    
    invoice_id = f"INV{str(uuid.uuid4())[:6].upper()}"
    invoice_code = f"CODE{str(uuid.uuid4())[:4].upper()}"
    invoice_date = datetime.now().date()
    
    # Convert to USD if needed (you'll need exchange rates)
    amount_usd = amount_original  # Placeholder - implement currency conversion
    
    cursor.execute('''
        INSERT INTO CRM_Invoice (InvoiceCode, InvoiceID, ServiceID, CustomerID, InvoiceDate, DueDate, AmountOriginal, AmountUSD, Status, Note, OutstandingUSD)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (invoice_code, invoice_id, service_id, customer_id, invoice_date, due_date, amount_original, amount_usd, 'Pending', notes, amount_usd))
    
    crm_conn.commit()
    crm_conn.close()
    return invoice_id

def get_invoices_by_service(service_id):
    """Get invoices for a specific service"""
    crm_conn = get_connection()
    try:
        df = pd.read_sql_query('SELECT * FROM CRM_Invoice WHERE ServiceID = ?', crm_conn, params=(service_id,))
    except Exception:
        df = pd.DataFrame()
    crm_conn.close()
    return df

def update_payment(payment_id, first_amount=None, first_date=None, second_amount=None, second_date=None):
    crm_conn = get_crm_connection()
    cursor = crm_conn.cursor()
    
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
        sql = f'UPDATE Payments SET {", ".join(updates)} WHERE PaymentID = ?'
        cursor.execute(sql, values)
        crm_conn.commit()
    
    crm_conn.close()


# --------------------------
# Document functions
# --------------------------
def add_document(customer_id, service_id, document_type, document_name, responsible_person, notes=""):
    """
    Store documents in SQL Server (ClientDocuments). responsible_person is a user id stored in auth.db.
    """
    crm_conn = get_crm_connection()
    cursor = crm_conn.cursor()

    doc_id = f"DOC{str(uuid.uuid4())[:6].upper()}"
    created_date = datetime.now().date()

    cursor.execute('''
        INSERT INTO ClientDocuments
        (DocumentID, CustomerID, ServiceID, DocumentType, DocumentName, ResponsiblePerson, Notes, CreatedDate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (doc_id, customer_id, service_id, document_type, document_name, responsible_person, notes, created_date))

    crm_conn.commit()
    crm_conn.close()
    return doc_id


def get_documents(user_id=None, user_role=None):
    """
    Fetch documents from SQL Server and enrich with auth.db (responsible_name + assigned/meta).
    Admins see documents for approved customers; others see docs for their assigned customers.
    Returns a pandas DataFrame.
    """
    # 1) Load documents + customer/service info from CRM
    crm_conn = get_crm_connection()
    try:
        docs_df = pd.read_sql_query('''
            SELECT cd.DocumentID, cd.CustomerID, cd.ServiceID, cd.DocumentType, cd.DocumentName,
                   cd.ResponsiblePerson, cd.Notes, cd.Status, cd.CreatedDate,
                   c.CompanyName, s.ServiceType
            FROM ClientDocuments cd
            JOIN Customers c ON cd.CustomerID = c.CustomerID
            LEFT JOIN Services s ON cd.ServiceID = s.ServiceID
        ''', crm_conn)
    except Exception:
        docs_df = pd.DataFrame()
    crm_conn.close()

    if docs_df.empty:
        return docs_df

    # 2) Load auth metadata from SQLite
    auth_conn = get_auth_connection()
    try:
        meta_df = pd.read_sql_query('SELECT CustomerID, assigned_to, status, approved FROM customer_meta', auth_conn)
    except Exception:
        meta_df = pd.DataFrame(columns=['CustomerID','assigned_to','status','approved'])
    try:
        users_df = pd.read_sql_query('SELECT id, name FROM users', auth_conn)
    except Exception:
        users_df = pd.DataFrame(columns=['id','name'])
    auth_conn.close()

    # 3) Merge
    df = docs_df.merge(meta_df, on='CustomerID', how='left')

    # map responsible_person -> name
    if not users_df.empty:
        users_df = users_df.rename(columns={'id': 'ResponsiblePerson', 'name': 'responsible_name'})
        df = df.merge(users_df, on='ResponsiblePerson', how='left')
    else:
        df['responsible_name'] = None

    # normalize flags
    df['approved'] = df['approved'].fillna(0).astype(int)
    df['status'] = df['status'].fillna('Chưa bắt đầu')

    # 4) filter by role
    if user_role == 'admin':
        df_filtered = df[df['approved'] == 1]
    else:
        df_filtered = df[(df['assigned_to'] == user_id) & (df['approved'] == 1)]

    return df_filtered.reset_index(drop=True)


def update_document_status(doc_id, new_status):
    """
    Update document status in SQL Server.
    """
    crm_conn = get_crm_connection()
    cursor = crm_conn.cursor()
    cursor.execute('UPDATE ClientDocuments SET Status = ? WHERE DocumentID = ?', (new_status, doc_id))
    crm_conn.commit()
    crm_conn.close()
    return True


# --------------------------
# Notification functions (SQLite auth.db)
# --------------------------
def get_notifications(user_id, user_role=None):
    auth_conn = get_auth_connection()
    if user_role == 'admin':
        query = '''
            SELECT n.*, u.name as target_user_name
            FROM notifications n
            LEFT JOIN users u ON n.user_id = u.id
            ORDER BY n.created_at DESC
        '''
        df = pd.read_sql_query(query, auth_conn)
    else:
        query = '''
            SELECT n.*, u.name as target_user_name
            FROM notifications n
            LEFT JOIN users u ON n.user_id = u.id
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC
        '''
        df = pd.read_sql_query(query, auth_conn, params=(user_id,))
    auth_conn.close()
    return df


def get_unread_count(user_id, user_role=None):
    auth_conn = get_auth_connection()
    cursor = auth_conn.cursor()
    if user_role == 'admin':
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE [read] = 0')
    else:
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND [read] = 0', (user_id,))
    count = cursor.fetchone()[0]
    auth_conn.close()
    return count


def mark_notification_read(notification_id):
    auth_conn = get_auth_connection()
    cursor = auth_conn.cursor()
    cursor.execute('UPDATE notifications SET [read] = 1 WHERE id = ?', (notification_id,))
    auth_conn.commit()
    auth_conn.close()
    return True


# --------------------------
# Dashboard stats (cross-db aggregation)
# --------------------------
def get_dashboard_stats():
    """Get dashboard statistics from actual tables"""
    try:
        crm_conn = get_connection()
        
        # Get basic counts
        customer_count = pd.read_sql_query("SELECT COUNT(*) as count FROM CRM_Customers", crm_conn)['count'].iloc[0]
        service_count = pd.read_sql_query("SELECT COUNT(*) as count FROM CRM_Services", crm_conn)['count'].iloc[0]
        invoice_count = pd.read_sql_query("SELECT COUNT(*) as count FROM CRM_Invoice", crm_conn)['count'].iloc[0]
        
        # Service status distribution
        service_status = pd.read_sql_query("SELECT Status, COUNT(*) as count FROM CRM_Services GROUP BY Status", crm_conn)
        task_stats = list(service_status.itertuples(index=False, name=None))
        
        crm_conn.close()
        
        return {
            'customer_count': customer_count,
            'service_count': service_count, 
            'invoice_count': invoice_count,
            'task_stats': task_stats,
            'customer_progress': [],  # Would need more complex query
            'overdue_tasks': []  # Would need WorkProgress table or equivalent
        }
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return {
            'customer_count': 0,
            'service_count': 0,
            'invoice_count': 0,
            'task_stats': [],
            'customer_progress': [],
            'overdue_tasks': []
        }

# --------------------------
# Login page (no DB change required; kept for completeness)
# --------------------------
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


# --------------------------
# show_customers (fixed edit / update to use SQL Server)
# --------------------------
def show_customers():
    st.header("Customer Management")
    
    # Add new customer (existing add_customer_enhanced handles cross-db correctly)
    with st.expander("Add New Customer"):
        with st.form("add_customer"):
            col1, col2 = st.columns(2)
            
            with col1:
                company_name = st.text_input("Company Name*")
                tax_code = st.text_input("Tax Code")
                
                # Get customer groups (from auth.db)
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
                
                company_type = st.text_input("Company Type", 
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
                
                # Assign to employee (from auth.db)
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
                        company_type, contact_person1, contact_email1, contact_phone1,
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
                    st.write(f"**Tax Code:** {customer.get('TaxCode') or 'N/A'}")
                    st.write(f"**Address:** {customer.get('Address') or 'N/A'}")
                    st.write(f"**Country:** {customer.get('Country')}")
                    st.write(f"**Category:** {customer.get('CustomerCategory')} - {customer.get('CompanyType')}")  # FIXED: use CompanyType
                    st.write(f"**Industry:** {customer.get('Industry') or 'N/A'}")
                    st.write(f"**Source:** {customer.get('Source') or 'N/A'}")
                
                with col2:
                    st.write(f"**Primary Contact:** {customer.get('ContactPerson1')}")
                    st.write(f"**Primary Email:** {customer.get('ContactEmail1') or 'N/A'}")
                    st.write(f"**Primary Phone:** {customer.get('ContactPhone1') or 'N/A'}")
                    if customer.get('ContactPerson2'):
                        st.write(f"**Secondary Contact:** {customer.get('ContactPerson2')}")
                        st.write(f"**Secondary Email:** {customer.get('ContactEmail2') or 'N/A'}")
                        st.write(f"**Secondary Phone:** {customer.get('ContactPhone2') or 'N/A'}")
                    st.write(f"**Assigned to:** {customer.get('assigned_name')}")
                    st.write(f"**Group:** {customer.get('GroupName') or 'N/A'}")
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                
                # Status update
                current_status = customer.get('status')
                can_edit = (st.session_state.user['role'] == 'admin' or 
                          customer.get('assigned_to') == st.session_state.user['id'])
                
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
                    if can_edit:
                        if st.button("Edit", key=f"edit_{customer['CustomerID']}"):
                            # Simple edit form (you can expand with more fields later)
                            with st.form(key=f"edit_form_{customer['CustomerID']}"):
                                new_name = st.text_input("Company Name", customer["CompanyName"])
                                new_address = st.text_input("Address", customer.get("Address", ""))
                                new_email = st.text_input("Contact Email", customer.get("ContactEmail1", ""))
                                submitted = st.form_submit_button("Save changes")
                                
                                if submitted:
                                    # FIXED: Update CRM_Customers table
                                    crm_conn = get_crm_connection()
                                    cursor = crm_conn.cursor()
                                    cursor.execute(
                                        """
                                        UPDATE CRM_Customers
                                        SET CompanyName = ?, Address = ?, ContactEmail1 = ?
                                        WHERE CustomerID = ?
                                        """,
                                        (new_name, new_address, new_email, customer["CustomerID"])
                                    )
                                    crm_conn.commit()
                                    crm_conn.close()
                                    st.success("Customer updated successfully!")
                                    st.rerun()  # FIXED: use st.rerun() instead of st.experimental_rerun()

                
                with col3:
                    # Delete button (admin only)
                    if st.session_state.user['role'] == 'admin':
                        if st.button("Delete", key=f"delete_{customer['CustomerID']}", type="secondary"):
                            # Confirmation dialog using session state
                            st.session_state[f"confirm_delete_{customer['CustomerID']}"] = True
                        
                        # Show confirmation if delete was clicked
                        if st.session_state.get(f"confirm_delete_{customer['CustomerID']}", False):
                            st.warning(f"Are you sure you want to delete {customer['CompanyName']}? This will also delete all related services and invoices.")
                            
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

# --------------------------
# Modified show_user_management function
# --------------------------
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
    
    # Display users (from auth.db)
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
                    # Get user's assigned customers count (from customer_meta in SQLite)
                    auth_conn = get_auth_connection()
                    cursor = auth_conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM customer_meta WHERE assigned_to = ?', (user['id'],))
                    customer_count = cursor.fetchone()[0]
                    auth_conn.close()
                    
                    st.write(f"**Assigned Customers:** {customer_count}")
                    
                    # Edit button (placeholder)
                    if st.button("Edit", key=f"edit_user_{user['id']}"):
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
                    st.write(f"**Category:** {customer['CustomerCategory']} - {customer['CompanyType']}")
                
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
                        st.success(f"Customer {customer['CompanyName']} approved!")
                        st.rerun()
                
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{customer['CustomerID']}"):
                        # FIXED: Simplified delete
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM CRM_Customers WHERE CustomerID = ?", (customer['CustomerID'],))
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

# Add this to the end of your app.py file

def main():
    st.set_page_config(
        page_title="CRM System",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize databases on startup
    if 'db_initialized' not in st.session_state:
        with st.spinner("Initializing databases..."):
            init_auth_database()  # Initialize SQLite auth.db
            init_database()       # Initialize SQL Server connection
            st.session_state.db_initialized = True
    
    # Check if user is logged in
    if 'user' not in st.session_state:
        login_page()
    else:
        show_dashboard()

def show_dashboard():
    """Main dashboard with sidebar navigation"""
    st.sidebar.title("Navigation")
    
    # Navigation menu
    if st.session_state.user['role'] == 'admin':
        menu_options = [
            "Dashboard",
            "Customer Management", 
            "Service Management",
            "Work Progress",
            "Document Management",
            "Payment Management",
            "User Management",
            "Customer Approvals",
            "Notifications",
            "Reports"
        ]
    else:
        menu_options = [
            "Dashboard",
            "Customer Management",
            "Service Management", 
            "Work Progress",
            "Document Management",
            "Payment Management",
            "Notifications"
        ]

    # Set default page if not exist
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Dashboard"
    
    # Navigation buttons
    for page in menu_options:
        if st.sidebar.button(page, key=f"nav_{page}", use_container_width=True):
            st.session_state.current_page = page
            st.rerun()
    
    # Get the current page for routing
    selected_page = st.session_state.current_page
    
    # Logout button
    if st.sidebar.button("Logout"):
        # Clear session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    # Display notifications count in sidebar
    if st.session_state.user:
        unread_count = get_unread_count(st.session_state.user['id'], st.session_state.user['role'])
        if unread_count > 0:
            st.sidebar.error(f"📢 {unread_count} unread notifications")
    
    # Route to appropriate page
    if selected_page == "Dashboard":
        show_dashboard_home()
    elif selected_page == "Customer Management":
        show_customers()
    elif selected_page == "Service Management":
        show_services()
    elif selected_page == "Work Progress":
        show_work_progress()
    elif selected_page == "Document Management":
        show_documents()
    elif selected_page == "Payment Management":
        show_payments()
    elif selected_page == "User Management":
        show_user_management()
    elif selected_page == "Customer Approvals":
        show_approvals()
    elif selected_page == "Notifications":
        show_notifications()
    elif selected_page == "Reports":
        show_reports()

def show_dashboard_home():
    """Dashboard home page with statistics"""
    st.title("📊 CRM Dashboard")
    
    # Get dashboard statistics
    stats = get_dashboard_stats()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
    services_df = get_all_services(st.session_state.user['id'], st.session_state.user['role'])
    
    with col1:
        st.metric("My Customers", len(customers_df))
    with col2:
        st.metric("Active Services", len(services_df))
    with col3:
        pending_count = len(get_pending_customers()) if st.session_state.user['role'] == 'admin' else 0
        st.metric("Pending Approvals", pending_count)
    with col4:
        unread_count = get_unread_count(st.session_state.user['id'], st.session_state.user['role'])
        st.metric("Unread Notifications", unread_count)
    
    # Task statistics
    if stats['task_stats']:
        st.subheader("📋 Task Overview")
        task_df = pd.DataFrame(stats['task_stats'], columns=['Status', 'Count'])
        st.bar_chart(task_df.set_index('Status'))
    
    # Recent activity or overdue tasks
    if stats['overdue_tasks']:
        st.subheader("⚠️ Overdue Tasks")
        overdue_df = pd.DataFrame(stats['overdue_tasks'], 
                                columns=['Task ID', 'Task Name', 'Status', 'Last Updated'])
        st.dataframe(overdue_df)
    
    # Customer progress
    if stats['customer_progress']:
        st.subheader("📈 Customer Progress")
        progress_df = pd.DataFrame(stats['customer_progress'], 
                                 columns=['Customer ID', 'Company', 'Total Tasks', 'Completed'])
        progress_df['Completion %'] = (progress_df['Completed'] / progress_df['Total Tasks'] * 100).round(1)
        st.dataframe(progress_df)

def get_crm_connection():
    return get_connection()

def show_services():
    """Service management page"""
    st.header("Service Management")
    
    # Add new service
    with st.expander("Add New Service"):
        with st.form("add_service"):
            customers_df = get_customers_enhanced(st.session_state.user['id'], st.session_state.user['role'])
            
            if len(customers_df) > 0:
                customer_id = st.selectbox("Customer", 
                                         options=customers_df['CustomerID'].tolist(),
                                         format_func=lambda x: f"{x} - {customers_df[customers_df['CustomerID']==x]['CompanyName'].iloc[0]}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    service_type = st.selectbox("Service Type", 
                                              ['Consulting', 'Development', 'Support', 'Training', 'Other'])
                    start_date = st.date_input("Start Date")
                    package_code = st.text_input("Package Code")
                
                with col2:
                    expected_end_date = st.date_input("Expected End Date")
                    partner = st.text_input("Partner")
                
                description = st.text_area("Service Description")
                
                submit_service = st.form_submit_button("Add Service")
                
                if submit_service:
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
                    st.write(f"**Start Date:** {service['StartDate']}")
                    st.write(f"**Expected End Date:** {service['ExpectedEndDate']}")
                
                with col2:
                    st.write(f"**Package Code:** {service.get('PackageCode', 'N/A')}")
                    st.write(f"**Partner:** {service.get('Partner', 'N/A')}")
                
                if service.get('Description'):
                    st.write(f"**Description:** {service['Description']}")
                
                # Quick action buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Add Task", key=f"task_{service['ServiceID']}"):
                        st.session_state.selected_service_for_task = service['ServiceID']
                        st.session_state.current_page = "Work Progress"
                        st.rerun()
                
                with col2:
                    if st.button("Add Payment", key=f"payment_{service['ServiceID']}"):
                        st.session_state.selected_service_for_payment = service['ServiceID']
                        st.session_state.current_page = "Payment Management"
                        st.rerun()
    else:
        st.info("No services found. Add your first service above!")

# Add missing utility functions
def delete_customer(customer_id):
    """Delete customer and related records"""
    try:
        crm_conn = get_connection()
        cursor = crm_conn.cursor()
        
        # Delete in order: invoices -> services -> customer
        cursor.execute("DELETE FROM CRM_Invoice WHERE CustomerID = ?", (customer_id,))
        cursor.execute("DELETE FROM CRM_Services WHERE CustomerID = ?", (customer_id,))
        cursor.execute("DELETE FROM CRM_Customers WHERE CustomerID = ?", (customer_id,))
        
        crm_conn.commit()
        crm_conn.close()
        
        # Delete from auth.db
        auth_conn = get_auth_connection()
        cursor = auth_conn.cursor()
        cursor.execute("DELETE FROM customer_meta WHERE CustomerID = ?", (customer_id,))
        cursor.execute("DELETE FROM notifications WHERE related_id = ?", (customer_id,))
        auth_conn.commit()
        auth_conn.close()
        
        return True, "Customer deleted successfully!"
    except Exception as e:
        return False, f"Error deleting customer: {str(e)}"

def delete_user(user_id):
    """Delete user from auth database"""
    try:
        auth_conn = get_auth_connection()
        cursor = auth_conn.cursor()
        
        # Update customer assignments to NULL
        cursor.execute("UPDATE customer_meta SET assigned_to = NULL WHERE assigned_to = ?", (user_id,))
        # Delete user notifications
        cursor.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        # Delete user
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        auth_conn.commit()
        auth_conn.close()
        
        return True, "User deleted successfully!"
    except Exception as e:
        return False, f"Error deleting user: {str(e)}"

def send_email(to_email, subject, body):
    """Send email notification (placeholder - configure with your SMTP settings)"""
    try:
        # Configure these with your actual SMTP settings
        smtp_server = "smtp.gmail.com"  # Replace with your SMTP server
        smtp_port = 587
        from_email = "your-email@company.com"  # Replace with your email
        from_password = "your-app-password"  # Replace with your app password
        
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, from_password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Email failed: {str(e)}"

# Run the application
if __name__ == "__main__":
    main()