import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ========================
# GOOGLE SHEETS CONNECTION
# ========================


# Define scope
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Load credentials from Streamlit secrets
@st.cache_resource
def init_connection():
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE
    )
    client = gspread.authorize(credentials)
    return client

# Initialize connection
client = init_connection()

# Sheets
SHEET_STUDENTS = "StudentScores"   # stores scores
SHEET_USERS = "Lecturers"          # stores lecturer login

sheet_students = client.open(SHEET_STUDENTS).sheet1
sheet_users = client.open(SHEET_USERS).sheet1



# ========================
# EMAIL CONFIGURATION
# ========================
# Configure these with your email settings
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USER = st.secrets["email"]["user"]
EMAIL_PASSWORD = st.secrets["email"]["password"]

# ========================
# HELPER FUNCTIONS
# ========================
def get_student_data():
    records = sheet_students.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        return df

    # Normalize column names
    df.columns = df.columns.str.strip().str.replace(" ", "_").str.title()
    return df

def get_lecturer_data():
    records = sheet_users.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        return df

    # Normalize column names
    df.columns = df.columns.str.strip().str.replace(" ", "_").str.title()
    return df

def update_score(index_number, course, score, ca):
    df = get_student_data()
    if df.empty:
        return

    try:
        # Locate row by both IndexNumber + Course
        row = df.index[(df["Indexnumber"] == index_number) & (df["Course"] == course)][0] + 2

        if "Score" in df.columns:
            sheet_students.update_cell(row, df.columns.get_loc("Score") + 1, score)
        if "Ca" in df.columns:
            sheet_students.update_cell(row, df.columns.get_loc("Ca") + 1, ca)
        if "Status" in df.columns:
            sheet_students.update_cell(row, df.columns.get_loc("Status") + 1, "Pending")
    except Exception as e:
        st.error(f"Error updating score: {e}")

def update_status(index_number, course, status):
    df = get_student_data()
    if df.empty:
        return

    try:
        row = df.index[(df["Indexnumber"] == index_number) & (df["Course"] == course)][0] + 2
        if "Status" in df.columns:
            sheet_students.update_cell(row, df.columns.get_loc("Status") + 1, status)
    except Exception as e:
        st.error(f"Error updating status: {e}")

def authenticate(username, password):
    users = sheet_users.get_all_records()
    # Convert input to lowercase for comparison
    username_lower = str(username).strip().lower()
    password_stripped = str(password).strip()
    
    for user in users:
        stored_username = str(user["Username"]).strip().lower()
        stored_password = str(user["Password"]).strip()
        
        if stored_username == username_lower and stored_password == password_stripped:
            # Return the original username from the sheet and role
            return str(user["Username"]).strip(), user["Role"]
    return None, None

def get_lecturer_students(lecturer_username, df):
    """Get students for a lecturer using case-insensitive matching"""
    if df.empty or "Lecturer" not in df.columns:
        return pd.DataFrame()
    
    # Create a case-insensitive mask
    lecturer_mask = df["Lecturer"].str.strip().str.lower() == lecturer_username.strip().lower()
    return df[lecturer_mask]

def send_notification_email(lecturer_name, lecturer_email, student_data):
    """Send notification email to lecturer"""
    # Fix: Properly assign the lecturer_name to the name variable
    name = lecturer_name
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = lecturer_email
        msg['Subject'] = "Postgraduate Result Request - CSI"

        # Create email body
        body = f"""
Dear Dr. {lecturer_name},

This is a friendly reminder to request for the results of the following student(s).

Students requiring result submission:

"""
        
        for _, student in student_data.iterrows():
            body += f"""
• Index Number: {student.get('Indexnumber', 'N/A')}
  Student Name: {student.get('Studentname', 'N/A')}
  Course: {student.get('Course', 'N/A')} - {student.get('Course_Title', 'N/A')}
  Academic Year: {student.get('Academic_Year', 'N/A')}
  Current Status: {student.get('Status', 'N/A')}
"""

        # Fix: Use the name variable to retrieve password from secrets
        lecturer_password = st.secrets["email"].get(name, "Contact admin for password")
        
        body += f"""

Please log into the Results Management System to submit the scores for these students.

System Access Details:
- Username: {lecturer_name}
- Password: {lecturer_password}
- Platform: https://postgrad-csi.streamlit.app/

If you have any questions or face technical difficulties, please contact the Postgraduate Coordinator.

Best regards,
Postgraduate Coordinator
Department of Computer Science and Informatics
"""

        msg.attach(MIMEText(body, 'plain'))

        # Connect to server and send email
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_USER, lecturer_email, text)
        server.quit()
        
        return True, "Email sent successfully"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# ========================
# STREAMLIT UI
# ========================
st.title("📊 Supplementary Results - CSI")

# Session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

# --- LOGIN ---
if not st.session_state.logged_in:
    with st.form("Login"):
        username = st.text_input("Enter username", placeholder="Username").strip()
        password = st.text_input("Enter password", type="password", placeholder="Password").strip()
        if st.form_submit_button("Login"):
            original_username, role = authenticate(username, password)
            if role:
                st.session_state.logged_in = True
                st.session_state.username = original_username  # Store original username from sheet
                st.session_state.role = role
                #st.success(f"Login Successful")
                st.rerun()
            else:
                st.error("Wrong login details")

else:
    st.sidebar.success(f"Logged in as {st.session_state.username} ({st.session_state.role})")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.role = None
        st.rerun()

    df = get_student_data()
    lecturer_df = get_lecturer_data()

    if df.empty:
        st.warning("⚠️ No student data found in sheet.")
    else:
        # --- USER PORTAL ---
        if st.session_state.role == "User":
            st.subheader("Enter / View Scores")

            # Use case-insensitive lecturer filtering
            lecturer_students = get_lecturer_students(st.session_state.username, df)

            if lecturer_students.empty:
                st.warning("No students assigned to you.")
            else:
                # Step 1: Select Student Index
                index_number = st.selectbox("Select Student Index Number", lecturer_students["Indexnumber"].unique())

                # Step 2: Select Course for that student
                student_courses = lecturer_students[lecturer_students["Indexnumber"] == index_number]["Course"].unique()
                course_code = st.selectbox("Select Course Code", student_courses)

                student_row = lecturer_students[
                    (lecturer_students["Indexnumber"] == index_number) & (lecturer_students["Course"] == course_code)
                ].iloc[0]

                # Display student info
                if "Studentname" in student_row:
                    st.write(f"**Student Name:** {student_row['Studentname']}")
                if "Course" in student_row:
                    st.write(f"**Course Code:** {student_row['Course']}")
                if "Course_Title" in student_row:
                    st.write(f"**Course Title:** {student_row['Course_Title']}")
                if "Score" in student_row:
                    st.write(f"**Current Score:** {student_row['Score']}")
                if "Ca" in student_row:
                    st.write(f"**Current CA:** {student_row['Ca']}")
                if "Status" in student_row:
                    st.write(f"**Current Status:** {student_row['Status']}")

                # Allow input if not approved
                if "Status" in student_row and student_row["Status"] != "Approved":
                    # Use a form to handle input and clearing
                    with st.form(key=f"score_form_{index_number}_{course_code}", clear_on_submit=True):
                        ca_input = st.number_input(
                            "Enter CA (Max: 40)", 
                            min_value=0.0,
                            max_value=40.0,
                            step=0.1,
                            format="%.1f",
                            help="CA score must be between 0 and 40"
                        )
                        score_input = st.number_input(
                            "Enter Exam Score (Max: 60)", 
                            min_value=0.0,
                            max_value=60.0,
                            step=0.1,
                            format="%.1f",
                            help="Exam score must be between 0 and 60"
                        )

                        submitted = st.form_submit_button("Submit Score")
                        
                        if submitted:
                            if ca_input > 0 and score_input > 0:
                                # Validate total score doesn't exceed 100
                                total_score = ca_input + score_input
                                if total_score <= 100:
                                    update_score(index_number, course_code, str(score_input), str(ca_input))
                                    st.success(f"✅ Score submitted for approval. Total: {total_score}")
                                    st.rerun()
                                else:
                                    st.error(f"Total score ({total_score}) cannot exceed 100. Please adjust your entries.")
                            else:
                                st.error("Please enter valid scores greater than 0 for both CA and Exam.")
                else:
                    st.info("Score is approved and locked. You cannot edit it.")

            st.subheader("📋 Your Students' Results")
            # Use case-insensitive filtering for display
            lecturer_results = get_lecturer_students(st.session_state.username, get_student_data())
            if not lecturer_results.empty:
                st.dataframe(lecturer_results)
            else:
                st.info("No students assigned to you.")

        # --- ADMIN PORTAL ---
        elif st.session_state.role == "Admin":
            # Create tabs for admin functions
            tab1, tab2 = st.tabs(["📋 Score Management", "📧 Lecturer Notifications"])
            
            with tab1:
                st.subheader("Admin Approval Dashboard")

                st.dataframe(df)

                if not df.empty:
                    index_number = st.selectbox("Select Student to Manage", df["Indexnumber"].unique())
                    student_courses = df[df["Indexnumber"] == index_number]["Course"].unique()
                    course_code = st.selectbox("Select Course Code", student_courses)

                    action = st.radio("Action", ["Approve", "Unlock for Editing"])

                    if st.button("Apply Action"):
                        if action == "Approve":
                            update_status(index_number, course_code, "Approved")
                            st.success(f"✅ Score for {index_number} - {course_code} approved.")
                        else:
                            update_status(index_number, course_code, "Editable")
                            st.success(f"🔓 Score for {index_number} - {course_code} unlocked for editing.")
                        st.rerun()
            
            with tab2:
                st.subheader("📧 Send Notification to Lecturers")
                
                # Email configuration section
                st.info("⚙️ **Email Configuration Required**: Please update the email settings in the code with your SMTP details.")
                
                if not df.empty and not lecturer_df.empty and "Lecturer" in df.columns:
                    # Get unique lecturers
                    unique_lecturers = df["Lecturer"].unique()
                    
                    selected_lecturer = st.selectbox(
                        "Select Lecturer to Notify", 
                        unique_lecturers,
                        help="Choose a lecturer to send result upload reminder"
                    )
                    
                    if selected_lecturer:
                        # Get lecturer's email
                        lecturer_email = get_lecturer_email(selected_lecturer, lecturer_df)
                        
                        # Get lecturer's students
                        lecturer_students_data = get_lecturer_students(selected_lecturer, df)
                        
                        if not lecturer_students_data.empty:
                            st.write(f"**Lecturer:** {selected_lecturer}")
                            if lecturer_email:
                                st.write(f"**Email:** {lecturer_email}")
                            else:
                                st.warning("⚠️ Email not found for this lecturer")
                            
                            st.write(f"**Number of Students:** {len(lecturer_students_data)}")
                            
                            # Show preview of students
                            with st.expander("👥 View Students Assigned to This Lecturer"):
                                display_cols = ["Indexnumber", "Studentname", "Course", "Course_Title", "Academic_Year", "Status"]
                                available_cols = [col for col in display_cols if col in lecturer_students_data.columns]
                                st.dataframe(lecturer_students_data[available_cols])
                            
                            # Send notification button
                            if lecturer_email:
                                if st.button(f"📧 Send Notification to {selected_lecturer}", type="primary"):
                                    with st.spinner("Sending email..."):
                                        success, message = send_notification_email(
                                            selected_lecturer, 
                                            lecturer_email, 
                                            lecturer_students_data
                                        )
                                    
                                    if success:
                                        st.success(f"✅ {message}")
                                        st.balloons()
                                    else:
                                        st.error(f"❌ {message}")
                            else:
                                st.warning("Cannot send email: Lecturer's email address not found.")
                        else:
                            st.info("No students assigned to this lecturer.")
                            
                    # Bulk notification option
                    st.divider()
                    st.subheader("📧 Bulk Notifications")
                    
                    if st.button("📧 Send Reminders to All Lecturers", type="secondary"):
                        if st.session_state.get('confirm_bulk_send', False):
                            with st.spinner("Sending bulk notifications..."):
                                success_count = 0
                                failed_count = 0
                                
                                for lecturer in unique_lecturers:
                                    lecturer_email = get_lecturer_email(lecturer, lecturer_df)
                                    lecturer_students_data = get_lecturer_students(lecturer, df)
                                    
                                    if lecturer_email and not lecturer_students_data.empty:
                                        success, _ = send_notification_email(
                                            lecturer, 
                                            lecturer_email, 
                                            lecturer_students_data
                                        )
                                        if success:
                                            success_count += 1
                                        else:
                                            failed_count += 1
                                
                                st.success(f"✅ Bulk notification complete! Sent: {success_count}, Failed: {failed_count}")
                                if success_count > 0:
                                    st.balloons()
                                st.session_state.confirm_bulk_send = False
                        else:
                            st.session_state.confirm_bulk_send = True
                            st.warning("⚠️ Click again to confirm bulk email sending to all lecturers.")
                else:
                    st.warning("⚠️ No student or lecturer data available for notifications.")
