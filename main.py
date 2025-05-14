from flask import Flask, render_template, request, flash, redirect, url_for, session
import pandas as pd
import os
from datetime import datetime
from models import db, Visitor, Admin
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()
    # Create admin user if not exists
    if not Admin.query.filter_by(username='admin').first():
        admin = Admin(
            username='Mithun',
            password=generate_password_hash('@Mithun#7411')
        )
        db.session.add(admin)
        db.session.commit()

def log_visitor(cet_number=None, marks=None):
    visitor = Visitor(
        cet_number=cet_number,
        marks=marks,
        ip_address=request.remote_addr
    )
    db.session.add(visitor)
    db.session.commit()

# Function to load and process the CSV data
def load_cet_data(filepath):
    try:
        # Try to read the CSV file
        df = pd.read_csv(filepath)
        
        # Check if required columns exist
        required_columns = ["CET No", "Marks", "Rank"]
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"CSV file is missing required column: {col}")
        
        # Convert 'Cet No' to string to ensure proper matching
        df["CET No"] = df["CET No"].astype(str)
        
        # Sort by marks in descending order
        df = df.sort_values(by="Marks", ascending=False)
        
        return df
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return None

# Function to calculate rank range
def calculate_rank_range(df, marks):
    # Get all students with the same marks
    same_marks_df = df[df["Marks"] == marks]
    
    if len(same_marks_df) > 0:
        # Get the minimum rank for these marks
        min_rank = same_marks_df["Rank"].min()
        
        # Count how many students have this mark (range size)
        num_students_same_mark = len(same_marks_df)
        
        # Calculate max rank (min rank + number of students with same mark - 1)
        max_rank = min_rank + num_students_same_mark - 1
        
        # Add 20 to the max rank for the upper bound of the range
        upper_bound = max_rank + 20
        
        return min_rank, upper_bound
    else:
        # If no exact match, find the closest ranks
        better_marks_count = len(df[df["Marks"] > marks])
        estimated_rank = better_marks_count + 1
        
        return estimated_rank, estimated_rank + 20

# Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    error = None
    
    # Check if CSV file exists
    csv_path = 'kcet_practicle.csv'
    if not os.path.exists(csv_path):
        error = "CET results data file is missing. Please provide the CSV file."
        return render_template('index.html', error=error)
    
    # Load data
    cet_data = load_cet_data(csv_path)
    if cet_data is None:
        error = "Could not process the CET results data. Please check the CSV file format."
        return render_template('index.html', error=error)
    
    if request.method == 'POST':
        cet_number = request.form.get('cet_number', '').strip()
        
        if not cet_number:
            flash('Please enter a CET Number', 'error')
        else:
            # Look up the CET number in the dataframe
            matching_row = cet_data[cet_data["CET No"] == cet_number]
            
            if matching_row.empty:
                flash(f'CET Number {cet_number} not found in the database. Please enter your marks to get an estimated rank range.', 'info')
                return redirect(url_for('manual_entry'))
            else:
                # Extract the data
                marks = matching_row["Marks"].values[0]
                
                # Log visitor
                log_visitor(cet_number=cet_number, marks=marks)
                
                # Create result dictionary
                result = {
                    'cet_number': cet_number,
                    'marks': marks,
                    'eligible': marks >= 100
                }
                
                # Only show rank range if marks are at least 100
                if marks >= 100:
                    # Calculate the rank range
                    min_rank, max_rank = calculate_rank_range(cet_data, marks)
                    result['rank_range'] = {
                        'min': min_rank,
                        'max': max_rank
                    }

    return render_template('index.html', result=result, error=error)

@app.route('/manual-entry', methods=['GET', 'POST'])
def manual_entry():
    result = None
    
    # Check if CSV file exists for rank estimation
    csv_path = 'kcet_practicle.csv'
    if not os.path.exists(csv_path):
        error = "CET results data file is missing. Cannot estimate rank range."
        return render_template('manual_entry.html', error=error)
    
    # Load data
    cet_data = load_cet_data(csv_path)
    if cet_data is None:
        error = "Could not process the CET results data. Cannot estimate rank range."
        return render_template('manual_entry.html', error=error)
    
    if request.method == 'POST':
        try:
            marks = float(request.form.get('marks', '0'))
            
            if marks < 0 or marks > 200:
                flash('Please enter valid marks between 0 and 200', 'error')
            else:
                # Estimate rank range based on marks
                if marks >= 100:
                    # Calculate rank range based on data
                    min_rank, max_rank = calculate_rank_range(cet_data, marks)
                    
                    # Create result with estimated rank range
                    # Log visitor for manual entry
                    log_visitor(marks=marks)
                    
                    result = {
                        'marks': marks,
                        'eligible': True,
                        'rank_range': {
                            'min': min_rank,
                            'max': max_rank
                        },
                        'total_candidates': len(cet_data)
                    }
                else:
                    # Log visitor for manual entry (ineligible)
                    log_visitor(marks=marks)
                    
                    result = {
                        'marks': marks,
                        'eligible': False,
                        'total_candidates': len(cet_data)
                    }
        except ValueError:
            flash('Please enter valid numeric marks', 'error')
    
    return render_template('manual_entry.html', result=result)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    ist_offset = timedelta(hours=5, minutes=30)  # IST is UTC+5:30
    today_ist = (datetime.utcnow() + ist_offset).date()
    stats = {
        'total_visitors': Visitor.query.count(),
        'today_visitors': Visitor.query.filter(db.func.date(Visitor.timestamp + ist_offset) == today_ist).count(),
        'avg_marks': db.session.query(db.func.avg(Visitor.marks)).scalar()
    }
    visitors = Visitor.query.order_by(Visitor.timestamp.desc()).limit(100).all()
    # Convert timestamps to IST for display
    for visitor in visitors:
        visitor.ist_timestamp = visitor.timestamp + ist_offset
    return render_template('admin_dashboard.html', stats=stats, visitors=visitors)

@app.route('/admin/export')
def export_data():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    visitors = Visitor.query.all()
    
    output = "CET Visitor Data Export\n"
    output += "=" * 50 + "\n\n"
    output += "Timestamp | CET Number | Marks | IP Address\n"
    output += "-" * 50 + "\n"
    
    for visitor in visitors:
        output += f"{visitor.timestamp} | {visitor.cet_number or 'N/A'} | {visitor.marks or 'N/A'} | {visitor.ip_address}\n"
    
    from flask import make_response
    response = make_response(output)
    response.headers['Content-Type'] = 'text/plain'
    response.headers['Content-Disposition'] = 'attachment; filename=visitor_data.txt'
    
    return response

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)