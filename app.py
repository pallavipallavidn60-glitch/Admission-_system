from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import json
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd
from io import BytesIO

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)  # This allows frontend to connect

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['DATABASE_FILE'] = 'students.json'

# Default eligibility criteria
ELIGIBILITY_CRITERIA = {
    'min_puc_percentage': 50,
    'min_sslc_percentage': 50,
    'min_cet_score': 60
}

# Email configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': '',
    'sender_password': '',
    'use_tls': True,
    'enabled': False
}

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)

def load_students():
    try:
        if os.path.exists(app.config['DATABASE_FILE']):
            with open(app.config['DATABASE_FILE'], 'r') as f:
                return json.load(f)
    except:
        pass
    return []

def save_students(students):
    with open(app.config['DATABASE_FILE'], 'w') as f:
        json.dump(students, f, indent=2, default=str)

def load_email_config():
    try:
        if os.path.exists('email_config.json'):
            with open('email_config.json', 'r') as f:
                config = json.load(f)
                config['enabled'] = bool(config.get('sender_email') and config.get('sender_password'))
                return config
    except:
        pass
    return None

def save_email_config_to_file(config):
    try:
        config_to_save = {k: v for k, v in config.items() if k != 'enabled'}
        with open('email_config.json', 'w') as f:
            json.dump(config_to_save, f, indent=2)
        return True
    except:
        return False

def send_email_notification(to_email, student_name, status, reason=None):
    email_config = load_email_config()
    if not email_config or not email_config.get('sender_email') or not email_config.get('sender_password'):
        return False, "Email not configured"
    
    try:
        msg = MIMEMultipart()
        msg['From'] = email_config['sender_email']
        msg['To'] = to_email
        msg['Subject'] = f"Admission Application Status - {student_name}"
        
        if status == 'approved':
            body = f"""
Dear {student_name},

🎉 CONGRATULATIONS! 🎉

Your admission application has been APPROVED!

Best regards,
Admission Committee
"""
        elif status == 'rejected':
            body = f"""
Dear {student_name},

We regret to inform you that your admission application has been REJECTED.

Reason: {reason if reason else 'You do not meet the minimum eligibility criteria'}

Best regards,
Admission Committee
"""
        else:
            body = f"""
Dear {student_name},

Your admission application has been received and is currently under review.

Status: PENDING

Best regards,
Admission Committee
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
        server.starttls()
        server.login(email_config['sender_email'], email_config['sender_password'])
        server.send_message(msg)
        server.quit()
        
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)

# Load saved config
saved_config = load_email_config()
if saved_config:
    EMAIL_CONFIG.update(saved_config)
    EMAIL_CONFIG['enabled'] = bool(EMAIL_CONFIG['sender_email'] and EMAIL_CONFIG['sender_password'])

# ==================== ROUTES ====================

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/register', methods=['POST'])
def register_student():
    try:
        form_data = request.form.to_dict()
        
        # Process photo
        photo_url = None
        if 'photo' in request.files and request.files['photo'].filename:
            photo = request.files['photo']
            ext = photo.filename.rsplit('.', 1)[1].lower() if '.' in photo.filename else 'jpg'
            filename = f"{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', filename)
            photo.save(filepath)
            photo_url = f"/uploads/photos/{filename}"
        
        # Calculate eligibility
        puc_percentage = float(form_data.get('puc_percentage', 0))
        sslc_percentage = float(form_data.get('sslc_percentage', 0))
        
        is_eligible = True
        reasons = []
        
        if puc_percentage < ELIGIBILITY_CRITERIA['min_puc_percentage']:
            is_eligible = False
            reasons.append(f"PUC {puc_percentage}% < {ELIGIBILITY_CRITERIA['min_puc_percentage']}%")
        
        if sslc_percentage < ELIGIBILITY_CRITERIA['min_sslc_percentage']:
            is_eligible = False
            reasons.append(f"SSLC {sslc_percentage}% < {ELIGIBILITY_CRITERIA['min_sslc_percentage']}%")
        
        cet_score = None
        if form_data.get('cet_qualified') == 'yes' and form_data.get('cet_score'):
            cet_score = float(form_data['cet_score'])
            if cet_score < ELIGIBILITY_CRITERIA['min_cet_score']:
                is_eligible = False
                reasons.append(f"CET {cet_score} < {ELIGIBILITY_CRITERIA['min_cet_score']}")
        
        status = 'pending' if is_eligible else 'rejected'
        
        student = {
            'id': str(uuid.uuid4()),
            'srn': form_data['srn'],
            'full_name': form_data['full_name'],
            'email': form_data['email'],
            'phone': form_data['phone'],
            'dob': form_data.get('dob', ''),
            'father_name': form_data.get('father_name', ''),
            'mother_name': form_data.get('mother_name', ''),
            'course': form_data['course'],
            'fees': float(form_data['fees']),
            'puc_percentage': puc_percentage,
            'sslc_percentage': sslc_percentage,
            'cet_qualified': form_data.get('cet_qualified'),
            'cet_score': cet_score,
            'achievements': request.form.getlist('achievements'),
            'photo_url': photo_url,
            'registered_at': datetime.now().isoformat(),
            'status': status,
            'eligible': is_eligible,
            'eligibility_reasons': reasons
        }
        
        students = load_students()
        students.append(student)
        save_students(students)
        
        return jsonify({'success': True, 'message': f'Registration successful! Status: {status.upper()}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/students', methods=['GET'])
def get_students():
    students = load_students()
    for s in students:
        if 'password' in s:
            del s['password']
    return jsonify(students)

@app.route('/student/<srn>', methods=['GET'])
def get_student(srn):
    students = load_students()
    student = next((s for s in students if s['srn'] == srn), None)
    if student and 'password' in student:
        del student['password']
    return jsonify(student) if student else jsonify({'error': 'Not found'}), 404

@app.route('/student/<srn>/status', methods=['PUT'])
def update_status(srn):
    data = request.get_json()
    new_status = data.get('status')
    students = load_students()
    student = next((s for s in students if s['srn'] == srn), None)
    if student:
        student['status'] = new_status
        save_students(students)
        
        email_sent = False
        if EMAIL_CONFIG['enabled']:
            success, _ = send_email_notification(student['email'], student['full_name'], new_status)
            email_sent = success
        
        return jsonify({'success': True, 'message': f'Status updated to {new_status}', 'email_sent': email_sent})
    return jsonify({'error': 'Student not found'}), 404

@app.route('/send-email', methods=['POST'])
def send_email_route():
    data = request.get_json()
    srn = data.get('srn')
    students = load_students()
    student = next((s for s in students if s['srn'] == srn), None)
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    if not EMAIL_CONFIG['enabled']:
        return jsonify({'success': False, 'error': 'Email not configured'}), 400
    
    success, message = send_email_notification(student['email'], student['full_name'], student.get('status', 'pending'))
    if success:
        return jsonify({'success': True, 'message': 'Email sent!'})
    return jsonify({'success': False, 'error': message}), 500

@app.route('/send-bulk-emails', methods=['POST'])
def send_bulk_emails():
    students = load_students()
    sent = 0
    failed = 0
    for student in students:
        success, _ = send_email_notification(student['email'], student['full_name'], student.get('status', 'pending'))
        if success:
            sent += 1
        else:
            failed += 1
    return jsonify({'success': True, 'sent': sent, 'failed': failed})

@app.route('/email/config', methods=['GET', 'POST'])
def email_config_route():
    global EMAIL_CONFIG
    if request.method == 'GET':
        return jsonify({
            'smtp_server': EMAIL_CONFIG['smtp_server'],
            'smtp_port': EMAIL_CONFIG['smtp_port'],
            'sender_email': EMAIL_CONFIG['sender_email'],
            'enabled': EMAIL_CONFIG['enabled']
        })
    else:
        data = request.get_json()
        new_config = {
            'smtp_server': data.get('smtp_server', 'smtp.gmail.com'),
            'smtp_port': int(data.get('smtp_port', 587)),
            'sender_email': data.get('sender_email', ''),
            'sender_password': data.get('sender_password', ''),
            'use_tls': True
        }
        if save_email_config_to_file(new_config):
            EMAIL_CONFIG.update(new_config)
            EMAIL_CONFIG['enabled'] = bool(EMAIL_CONFIG['sender_email'] and EMAIL_CONFIG['sender_password'])
            return jsonify({'success': True, 'message': 'Email configuration saved', 'enabled': EMAIL_CONFIG['enabled']})
        return jsonify({'success': False, 'error': 'Failed to save'}), 500

@app.route('/test-email', methods=['POST'])
def test_email():
    data = request.get_json()
    test_email = data.get('test_email')
    smtp_server = data.get('smtp_server', 'smtp.gmail.com')
    smtp_port = int(data.get('smtp_port', 587))
    sender_email = data.get('sender_email', '')
    sender_password = data.get('sender_password', '')
    
    if not sender_email or not sender_password:
        return jsonify({'success': False, 'error': 'Please configure email settings first'}), 400
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = test_email
        msg['Subject'] = "Test Email - Admission System"
        body = f"This is a test email from your Admission System.\n\nSent at: {datetime.now()}"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return jsonify({'success': True, 'message': 'Test email sent successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/eligibility/criteria', methods=['GET', 'POST'])
def criteria_route():
    global ELIGIBILITY_CRITERIA
    if request.method == 'GET':
        return jsonify(ELIGIBILITY_CRITERIA)
    else:
        data = request.get_json()
        if 'min_puc' in data:
            ELIGIBILITY_CRITERIA['min_puc_percentage'] = float(data['min_puc'])
        if 'min_sslc' in data:
            ELIGIBILITY_CRITERIA['min_sslc_percentage'] = float(data['min_sslc'])
        if 'min_cet' in data:
            ELIGIBILITY_CRITERIA['min_cet_score'] = float(data['min_cet'])
        return jsonify({'success': True, 'message': 'Criteria updated'})

@app.route('/export/students', methods=['GET'])
def export_students():
    students = load_students()
    data = []
    for s in students:
        data.append({
            'SRN': s.get('srn'), 'Name': s.get('full_name'), 'Email': s.get('email'),
            'Phone': s.get('phone'), 'Course': s.get('course'), 'PUC': s.get('puc_percentage'),
            'SSLC': s.get('sslc_percentage'), 'CET': s.get('cet_score', 'N/A'),
            'Status': s.get('status'), 'Eligible': 'Yes' if s.get('eligible') else 'No'
        })
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Students', index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'students_{datetime.now().strftime("%Y%m%d")}.xlsx')

@app.route('/students/clear', methods=['POST'])
def clear_students():
    data = request.get_json()
    if data.get('password') != 'admin123':
        return jsonify({'error': 'Unauthorized'}), 401
    save_students([])
    return jsonify({'success': True, 'message': 'All data cleared'})

@app.route('/uploads/<path:filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE_FILE']):
        save_students([])
    
    print("=" * 50)
    print("🎓 University Admission System")
    print("=" * 50)
    print(f"✅ Server running on: http://localhost:5000")
    print(f"📧 Email configured: {'YES' if EMAIL_CONFIG['enabled'] else 'NO'}")
    print(f"📊 Database: {app.config['DATABASE_FILE']}")
    print("=" * 50)
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    app.run(debug=True, port=5000, host='0.0.0.0')