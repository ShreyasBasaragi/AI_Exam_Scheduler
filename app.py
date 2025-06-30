from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify, flash, g
import mysql.connector
import pandas as pd
import random
from datetime import datetime, timedelta, date
from io import BytesIO
import calendar
import time
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Set a secure secret key

@contextmanager
def get_db_connection_safe():
    conn = None
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Shreyas",
            database="ai_exam_scheduler_2"
        )
        yield conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

# Add custom strftime filter
@app.template_filter('strftime')
def strftime_filter(date, format):
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    return date.strftime(format)

# Database connection function
def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Shreyas",
        database="ai_exam_scheduler_2"
    )
    return conn

# Helper function to get classes based on scheduling scope
def get_classes_for_scheduling(dept_id=None, year_id=None, division_id=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT c.*, d.dept_name, y.year_name, dv.division_name
            FROM classes c
            JOIN departments d ON c.dept_id = d.dept_id
            JOIN years y ON c.year_id = y.year_id
            JOIN divisions dv ON c.division_id = dv.division_id
            WHERE c.dept_id = %s AND c.year_id = %s
        """
        params = [dept_id, year_id]
        
        if division_id:
            query += " AND c.division_id = %s"
            params.append(division_id)
        
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# Helper function to get years for a department
def get_years_for_department(dept_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT y.year_id, y.year_name
            FROM years y
            ORDER BY y.year_id
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# Helper function to get divisions for a year in a department
def get_divisions_for_year(dept_id, year_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT DISTINCT dv.division_id, dv.division_name
            FROM classes c
            JOIN divisions dv ON c.division_id = dv.division_id
            WHERE c.dept_id = %s AND c.year_id = %s
            ORDER BY dv.division_id
        """, (dept_id, year_id))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# Genetic Algorithm Parameters
POPULATION_SIZE = 50
GENERATIONS = 100
MUTATION_RATE = 0.3
CROSSOVER_RATE = 0.8

# Helper function to get weekdays between two dates
def get_weekdays(start_date, end_date):
    days = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Monday-Friday only
            days.append(current_date)
        current_date += timedelta(days=1)
    return days

def has_class_conflict_on_date(class_id, date, schedule, existing_exams, faculty_preferred_dates=None):
    """Check if a class has any exam scheduled on a given date"""
    date_str = date.strftime('%Y-%m-%d')
    
    # Check against existing exams (master_schedule)
    for ex in existing_exams:
        if ex['exam_date'].strftime('%Y-%m-%d') == date_str and ex['class_id'] == class_id:
            return True
    
    # Check against faculty preferred dates
    if faculty_preferred_dates:
        for pref in faculty_preferred_dates:
            if pref['exam_date'].strftime('%Y-%m-%d') == date_str and pref['class_id'] == class_id:
                return True
    
    # Check against current schedule
    for exam in schedule:
        if exam['exam_date'].strftime('%Y-%m-%d') == date_str and exam['class_id'] == class_id:
            return True
    
    return False

def has_conflicts(exam, date, schedule, existing_exams, faculty_preferred_dates=None):
    """Check if scheduling an exam on a given date would cause conflicts"""
    date_str = date.strftime('%Y-%m-%d')
    
    # 1. Check for class/division conflicts
    for ex in existing_exams:
        if ex['exam_date'].strftime('%Y-%m-%d') == date_str and ex['class_id'] == exam['class_id']:
            return True
    
    if faculty_preferred_dates:
        for pref in faculty_preferred_dates:
            if pref['exam_date'].strftime('%Y-%m-%d') == date_str and pref['class_id'] == exam['class_id']:
                return True
    
    for other in schedule:
        if other is not exam and other['exam_date'].strftime('%Y-%m-%d') == date_str and other['class_id'] == exam['class_id']:
            return True
    
    # 2. Check for faculty conflicts (same faculty can't have exams on same day)
    for ex in existing_exams:
        if ex['exam_date'].strftime('%Y-%m-%d') == date_str and ex['faculty_id'] == exam['faculty_id']:
            return True
    
    if faculty_preferred_dates:
        for pref in faculty_preferred_dates:
            if pref['exam_date'].strftime('%Y-%m-%d') == date_str and pref['faculty_id'] == exam['faculty_id']:
                return True
    
    for other in schedule:
        if other is not exam and other['exam_date'].strftime('%Y-%m-%d') == date_str and other['faculty_id'] == exam['faculty_id']:
            return True
    
    # 3. Check for room conflicts
    for ex in existing_exams:
        if ex['exam_date'].strftime('%Y-%m-%d') == date_str and ex['room_id'] == exam['room_id']:
            # For lab rooms, we can't have multiple divisions using the same lab on same day
            if exam['exam_type_id'] == 1 or ex['exam_type_id'] == 1:  # Lab exam type
                return True
            # For regular rooms, we can have different divisions using same room
            if exam['class_id'] == ex['class_id']:  # Same division
                return True
    
    if faculty_preferred_dates:
        for pref in faculty_preferred_dates:
            if pref['exam_date'].strftime('%Y-%m-%d') == date_str and pref['room_id'] == exam['room_id']:
                if exam['exam_type_id'] == 1 or pref['exam_type_id'] == 1:  # Lab exam type
                    return True
                if exam['class_id'] == pref['class_id']:  # Same division
                    return True
    
    for other in schedule:
        if other is not exam and other['exam_date'].strftime('%Y-%m-%d') == date_str and other['room_id'] == exam['room_id']:
            if exam['exam_type_id'] == 1 or other['exam_type_id'] == 1:  # Lab exam type
                return True
            if exam['class_id'] == other['class_id']:  # Same division
                return True
    
    return False

def repair_schedule(schedule, existing_exams, available_dates, constraints):
    """Repair a schedule to ensure it meets all constraints."""
    repaired = []
    
    # 1) First, keep all locked (faculty-preferred) exams
    for ex in schedule:
        if ex.get('is_faculty_preferred', False):
            repaired.append(ex)
    
    # 2) Now repair the rest
    for ex in schedule:
        if ex.get('is_faculty_preferred', False):
            continue  # already added
        
        orig_date = ex['exam_date']
        ex_type = ex['exam_type_id']
        
        # Build the list of valid dates for this exam type
        drange = constraints['exam_date_ranges'][str(ex_type)]
        valid_dates = sorted(d for d in available_dates
                             if drange['start_date'] <= d <= drange['end_date'])
        
        # If current date conflicts, or if it's not in the allowed range, find a new one
        if (orig_date not in valid_dates) or has_conflicts(ex, orig_date, repaired, existing_exams):
            for candidate in valid_dates:
                if not has_conflicts(ex, candidate, repaired, existing_exams):
                    ex['exam_date'] = candidate
                    break
            # if *all* dates conflict, we'll just keep the original date and accept the penalty
        repaired.append(ex)
    
    return repaired

# Fitness function for genetic algorithm
def calculate_fitness(schedule, constraints):
    penalty = 0
    faculty_dates = {}
    for exam in schedule:
        date_str = exam['exam_date'].strftime('%Y-%m-%d')
        key = f"{date_str}_{exam['faculty_id']}"
        if key in faculty_dates:
            penalty += 200
        else:
            faculty_dates[key] = True
    
    room_dates = {}
    for exam in schedule:
        date_str = exam['exam_date'].strftime('%Y-%m-%d')
        key = f"{date_str}_{exam['room_id']}"
        if key in room_dates:
            penalty += 200
        else:
            room_dates[key] = True
    
    # Heavily penalize class/division conflicts
    class_dates = {}
    for exam in schedule:
        date_str = exam['exam_date'].strftime('%Y-%m-%d')
        key = f"{date_str}_{exam['class_id']}"
        if key in class_dates:
            penalty += 5000  # Increased penalty for class conflicts
        else:
            class_dates[key] = True
    
    # Penalize lab room mismatches
    for exam in schedule:
        if exam['exam_type_id'] == 1:
            if exam['room_id'] != exam['designated_lab_id']:
                penalty += 200
    
    # Penalize conflicts with existing exams
    for exam in schedule:
        exam_date_str = exam['exam_date'].strftime('%Y-%m-%d')
        for existing in constraints.get('existing_exams', []):
            existing_date_str = (existing['exam_date'].strftime('%Y-%m-%d')
                               if hasattr(existing['exam_date'], 'strftime') else str(existing['exam_date']))
            if exam_date_str == existing_date_str:
                if exam['faculty_id'] == existing['faculty_id']:
                    penalty += 200
                if exam['room_id'] == existing['room_id']:
                    penalty += 200
                if exam['class_id'] == existing['class_id']:
                    penalty += 5000  # Increased penalty for conflicts with existing exams
    
    return 10000 - penalty  # Increased base score to accommodate higher penalties

# Create initial population
def create_initial_population(constraints, population_size):
    if not constraints['available_dates']:
        raise ValueError("No available dates provided. Check start and end dates.")
    population = []
    
    for _ in range(population_size):
        schedule = []
        scheduled_dates = set()  # Track scheduled dates to avoid clashes
        
        # Schedule exams using genetic algorithm
        for exam in constraints['exams_to_schedule']:
            exam_type_id = exam['exam_type_id']
            date_range = constraints['exam_date_ranges'][str(exam_type_id)]
            available_dates = [d for d in constraints['available_dates'] 
                             if date_range['start_date'] <= d <= date_range['end_date']]
            
            if not available_dates:
                raise ValueError(f"No available dates for exam type {exam_type_id}")
            
            # Try to find a date that doesn't conflict with existing exams or master schedule
            valid_date_found = False
            selected_date = None
            
            # For lab exams, use designated lab room, otherwise use class's assigned room
            if exam['exam_type_id'] == 1:  # Lab exam
                room_id = exam['designated_lab_id']
                for d in available_dates:
                    date_key = (exam['class_id'], d.strftime('%Y-%m-%d'))
                    if (date_key not in scheduled_dates and
                        not any(s['room_id'] == room_id and s['exam_date'] == d for s in schedule) and
                        not any(s['room_id'] == room_id and s['exam_date'] == d for s in constraints.get('existing_exams', []))):
                        selected_date = d
                        valid_date_found = True
                        break
            else:  # Non-lab exam (CVV, CP, PPT, etc.)
                room_id = exam['assigned_room_id']  # Use class's home room
                # Sort available dates to try earlier dates first
                available_dates.sort()
                for d in available_dates:
                    date_key = (exam['class_id'], d.strftime('%Y-%m-%d'))
                    if (date_key not in scheduled_dates and
                        not any(s['faculty_id'] == exam['faculty_id'] and s['exam_date'] == d for s in schedule) and
                        not any(s['room_id'] == room_id and s['exam_date'] == d for s in schedule) and
                        not any(s['faculty_id'] == exam['faculty_id'] and s['exam_date'] == d for s in constraints.get('existing_exams', [])) and
                        not any(s['room_id'] == room_id and s['exam_date'] == d for s in constraints.get('existing_exams', []))):
                        selected_date = d
                        valid_date_found = True
                        break
            
            if not valid_date_found:
                # If no valid date found, try to find any date within the exam type's range
                for d in available_dates:
                    date_key = (exam['class_id'], d.strftime('%Y-%m-%d'))
                    if date_key not in scheduled_dates:
                        selected_date = d
                        break
                if not selected_date:
                    selected_date = random.choice(available_dates)
            
            exam_entry = {
                'class_id': exam['class_id'],
                'subject_id': exam['subject_id'],
                'exam_type_id': exam['exam_type_id'],
                'faculty_id': exam['faculty_id'],
                'room_id': room_id,
                'exam_date': selected_date,
                'assigned_room_id': exam['assigned_room_id'],
                'designated_lab_id': exam['designated_lab_id']
            }
            schedule.append(exam_entry)
            scheduled_dates.add((exam['class_id'], selected_date.strftime('%Y-%m-%d')))
        
        repaired_schedule = repair_schedule(schedule, constraints['existing_exams'], constraints['available_dates'], constraints)
        population.append(repaired_schedule)
    return population

def crossover(parent1, parent2):
    exam_keys = [f"{exam['class_id']}_{exam['subject_id']}_{exam['exam_type_id']}" for exam in parent1]
    if len(exam_keys) < 2:
        return parent1, parent2
    crossover_point = random.randint(1, len(exam_keys) - 1)
    child1 = parent1.copy()
    child2 = parent2.copy()
    for i in range(crossover_point, len(exam_keys)):
        key = exam_keys[i]
        child1_idx = next(j for j, exam in enumerate(child1) if f"{exam['class_id']}_{exam['subject_id']}_{exam['exam_type_id']}" == key)
        child2_idx = next(j for j, exam in enumerate(child2) if f"{exam['class_id']}_{exam['subject_id']}_{exam['exam_type_id']}" == key)
        temp_date = child1[child1_idx]['exam_date']
        child1[child1_idx]['exam_date'] = child2[child2_idx]['exam_date']
        child2[child2_idx]['exam_date'] = temp_date
    return child1, child2

def mutate(schedule, constraints):
    if not schedule:
        return schedule
    if random.random() > MUTATION_RATE:
        return schedule
    
    # Select a random exam to mutate
    mutation_idx = random.randint(0, len(schedule) - 1)
    exam = schedule[mutation_idx]
    
    # Get available dates for this exam type
    exam_type_id = exam['exam_type_id']
    date_range = constraints['exam_date_ranges'][str(exam_type_id)]
    available_dates = [d for d in constraints['available_dates'] 
                      if date_range['start_date'] <= d <= date_range['end_date']]
    
    if available_dates:
        exam['exam_date'] = random.choice(available_dates)
    
    return schedule

def heavy_mutation(schedule, available_dates, constraints, mutation_probability=0.5):
    new_schedule = []
    for exam in schedule:
        new_exam = exam.copy()
        if random.random() < mutation_probability:
            # Get available dates for this exam type
            exam_type_id = exam['exam_type_id']
            date_range = constraints['exam_date_ranges'][str(exam_type_id)]
            available_dates_for_type = [d for d in available_dates 
                                      if date_range['start_date'] <= d <= date_range['end_date']]
            
            if available_dates_for_type:
                new_exam['exam_date'] = random.choice(available_dates_for_type)
        new_schedule.append(new_exam)
    return new_schedule

def run_genetic_algorithm(constraints):
    population = create_initial_population(constraints, POPULATION_SIZE)
    for generation in range(GENERATIONS):
        population = [repair_schedule(schedule, constraints['existing_exams'], constraints['available_dates'], constraints) for schedule in population]
        fitness_scores = [calculate_fitness(schedule, constraints) for schedule in population]
        parents = []
        for _ in range(POPULATION_SIZE):
            tournament_size = 3
            tournament_indices = random.sample(range(POPULATION_SIZE), tournament_size)
            tournament_fitness = [fitness_scores[i] for i in tournament_indices]
            winner_idx = tournament_indices[tournament_fitness.index(max(tournament_fitness))]
            parents.append(population[winner_idx])
        next_population = []
        for i in range(0, POPULATION_SIZE, 2):
            if i + 1 < POPULATION_SIZE:
                child1, child2 = crossover(parents[i], parents[i + 1])
                child1 = mutate(child1, constraints)
                child2 = mutate(child2, constraints)
                next_population.extend([child1, child2])
            else:
                next_population.append(parents[i])
        best_idx = fitness_scores.index(max(fitness_scores))
        next_population[0] = population[best_idx]
        population = next_population
    population = [repair_schedule(schedule, constraints['existing_exams'], constraints['available_dates'], constraints) for schedule in population]
    fitness_scores = [calculate_fitness(schedule, constraints) for schedule in population]
    sorted_population = [x for _, x in sorted(zip(fitness_scores, population), key=lambda pair: pair[0], reverse=True)]
    
    best_schedule = sorted_population[0]
    unique_schedules = [best_schedule]
    attempts = 0
    max_attempts = 20
    while len(unique_schedules) < 3 and attempts < max_attempts:
        candidate = heavy_mutation(best_schedule, constraints['available_dates'], constraints)
        candidate = repair_schedule(candidate, constraints['existing_exams'], constraints['available_dates'], constraints)
        candidate_tuple = tuple((exam['class_id'], exam['subject_id'], exam['exam_type_id'], exam['exam_date'].strftime('%Y-%m-%d')) for exam in candidate)
        existing_tuples = {tuple((exam['class_id'], exam['subject_id'], exam['exam_type_id'], exam['exam_date'].strftime('%Y-%m-%d')) for exam in s) for s in unique_schedules}
        if candidate_tuple not in existing_tuples:
            unique_schedules.append(candidate)
        attempts += 1
    while len(unique_schedules) < 3:
        unique_schedules.append(best_schedule)
    return unique_schedules

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get departments
        cursor.execute("SELECT * FROM departments")
        departments = cursor.fetchall()
        
        # Get modules
        cursor.execute("SELECT * FROM modules")
        modules = cursor.fetchall()
        
        # Get exam types
        cursor.execute("SELECT * FROM exam_types")
        exam_types = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('index.html', 
                             departments=departments, 
                             modules=modules,
                             exam_types=exam_types)
    except mysql.connector.Error as err:
        print(f"Database error in index route: {err}")
        return "Database connection error", 500
    except Exception as e:
        print(f"Error in index route: {str(e)}")
        return "An error occurred", 500

@app.route('/get_years/<int:dept_id>')
def get_years(dept_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all years directly from years table
        cursor.execute("""
            SELECT y.year_id, y.year_name
            FROM years y
            ORDER BY y.year_id
        """)
        years = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(years)
    except Exception as e:
        print(f"Error in get_years endpoint: {str(e)}")
        return jsonify([])

@app.route('/get_divisions/<int:dept_id>/<int:year_id>')
def get_divisions(dept_id, year_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT DISTINCT dv.division_id, dv.division_name
            FROM classes c
            JOIN divisions dv ON c.division_id = dv.division_id
            WHERE c.dept_id = %s AND c.year_id = %s
            ORDER BY dv.division_id
        """, (dept_id, year_id))
        divisions = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(divisions)
    except Exception as e:
        print(f"Error in get_divisions endpoint: {str(e)}")
        return jsonify([])

@app.route('/generate_schedules', methods=['POST'])
def generate_schedules():
    try:
        dept_id = request.form.get('dept_id')
        year_id = request.form.get('year_id')
        division_id = request.form.get('division_id')
        module_id = request.form.get('module_id')
        semester_input = request.form.get('semester')
        
        # Store department and year IDs in session
        session['dept_id'] = dept_id
        session['year_id'] = year_id
        session['module_id'] = module_id
        session['semester'] = semester_input
        session['division_id'] = division_id
        
        # Get selected exam types and their date ranges
        exam_types = request.form.getlist('exam_types[]')
        if not exam_types:
            return "No exam types selected", 400
        
        exam_date_ranges = {}
        for exam_type_id in exam_types:
            start_date = request.form.get(f'start_date_{exam_type_id}')
            end_date = request.form.get(f'end_date_{exam_type_id}')
            if not start_date or not end_date:
                return f"Missing date range for exam type {exam_type_id}", 400
            exam_date_ranges[exam_type_id] = {
                'start_date': datetime.strptime(start_date, "%Y-%m-%d"),
                'end_date': datetime.strptime(end_date, "%Y-%m-%d")
            }
        
        # Validate inputs
        if not all([dept_id, year_id, module_id, semester_input]):
            return "Missing required fields", 400
        
        # Get classes based on scheduling scope
        classes = get_classes_for_scheduling(dept_id, year_id, division_id)
        if not classes:
            return "No classes found for the selected criteria", 404
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1) Gather every exam across all classes
        global_exams = []
        all_existing_exams = []
        locked_exams = []  # Store locked faculty preferred exams
        
        for class_data in classes:
            class_id = class_data['class_id']
            assigned_room_id = class_data['assigned_room_id']
            
            # Get all available rooms for this class
            cursor.execute("""
                SELECT r.room_id, r.room_number
                FROM rooms r
                WHERE r.room_id = %s
            """, (assigned_room_id,))
            available_rooms = [row['room_id'] for row in cursor.fetchall()]
            
            # Add lab rooms if they exist
            cursor.execute("""
                SELECT r.room_id, r.room_number
                FROM rooms r
                JOIN subject_labs sl ON r.room_id = sl.room_id
                JOIN subject_class_module scm ON sl.subject_id = scm.subject_id
                WHERE scm.class_id = %s
            """, (class_id,))
            lab_rooms = [row['room_id'] for row in cursor.fetchall()]
            available_rooms.extend(lab_rooms)
            available_rooms = list(set(available_rooms))  # Remove duplicates
            
            # Get subjects and their exam types
            cursor.execute("""
                SELECT scm.subject_id, s.subject_name, scm.faculty_id, f.faculty_name
                FROM subject_class_module scm
                JOIN subjects s ON scm.subject_id = s.subject_id
                JOIN faculty f ON scm.faculty_id = f.faculty_id
                WHERE scm.class_id = %s
            """, (class_id,))
            subjects = cursor.fetchall() or []
            
            if not subjects:
                continue  # Skip classes with no subjects for the selected module
            
            # Build exams for this class
            for subject in subjects:
                # Get all exam types for this subject
                cursor.execute("""
                    SELECT se.exam_type_id, et.exam_type_name
                    FROM subject_exam_types se
                    JOIN exam_types et ON se.exam_type_id = et.exam_type_id
                    WHERE se.subject_id = %s
                """, (subject['subject_id'],))
                subject_exam_types = cursor.fetchall()
                
                # Filter to only include selected exam types
                subject_exam_types = [et for et in subject_exam_types if str(et['exam_type_id']) in exam_types]
                
                for exam_type in subject_exam_types:
                    designated_lab_id = None
                    if exam_type['exam_type_id'] == 1:  # Lab exam
                        cursor.execute("""
                            SELECT room_id FROM subject_labs
                            WHERE subject_id = %s AND class_id = %s
                        """, (subject['subject_id'], class_id))
                        lab_data = cursor.fetchone()
                        if lab_data:
                            designated_lab_id = lab_data['room_id']
                    
                    exam = {
                        'subject_id': subject['subject_id'],
                        'subject_name': subject['subject_name'],
                        'faculty_id': subject['faculty_id'],
                        'faculty_name': subject['faculty_name'],
                        'exam_type_id': exam_type['exam_type_id'],
                        'exam_type_name': exam_type['exam_type_name'],
                        'class_id': class_id,
                        'assigned_room_id': assigned_room_id,
                        'designated_lab_id': designated_lab_id,
                        'date_range': exam_date_ranges[str(exam_type['exam_type_id'])]
                    }
                    global_exams.append(exam)
            
            # Get existing exams from master_schedule
            cursor.execute("""
                SELECT class_id, subject_id, exam_type_id, faculty_id, room_id, exam_date
                FROM master_schedule
                WHERE class_id = %s
            """, (class_id,))
            for exam in cursor.fetchall():
                if isinstance(exam['exam_date'], str):
                    exam['exam_date'] = datetime.strptime(exam['exam_date'], '%Y-%m-%d')
                elif isinstance(exam['exam_date'], date):
                    exam['exam_date'] = datetime.combine(exam['exam_date'], datetime.min.time())
                all_existing_exams.append(exam)

            # Get faculty preferred dates and convert them to locked exams
            cursor.execute("""
                SELECT 
                    fpd.class_id,
                    fpd.subject_id,
                    fpd.exam_type_id,
                    fpd.faculty_id,
                    fpd.preferred_date AS exam_date,
                    CASE
                        WHEN fpd.exam_type_id = 1 THEN sl.room_id
                        ELSE c.assigned_room_id
                    END AS room_id
                FROM faculty_preferred_dates fpd
                JOIN classes c 
                    ON fpd.class_id = c.class_id
                LEFT JOIN subject_labs sl 
                    ON fpd.subject_id = sl.subject_id 
                    AND fpd.class_id = sl.class_id
                WHERE fpd.class_id = %s
            """, (class_id,))
            for pref in cursor.fetchall():
                if isinstance(pref['exam_date'], str):
                    pref['exam_date'] = datetime.strptime(pref['exam_date'], '%Y-%m-%d')
                elif isinstance(pref['exam_date'], date):
                    pref['exam_date'] = datetime.combine(pref['exam_date'], datetime.min.time())
                
                # Create a locked exam entry
                locked_exam = {
                    'class_id': pref['class_id'],
                    'subject_id': pref['subject_id'],
                    'exam_type_id': pref['exam_type_id'],
                    'faculty_id': pref['faculty_id'],
                    'room_id': pref['room_id'],
                    'exam_date': pref['exam_date'],
                    'is_faculty_preferred': True
                }
                locked_exams.append(locked_exam)

        # Remove any exams from global_exams that are already in locked_exams
        global_exams = [e for e in global_exams 
                       if not any(
                           e['class_id'] == l['class_id'] and
                           e['subject_id'] == l['subject_id'] and
                           e['exam_type_id'] == l['exam_type_id']
                       for l in locked_exams)]

        # 2) Compute available dates across all exam types
        all_available_dates = []
        for exam_type_id in exam_types:
            date_range = exam_date_ranges[exam_type_id]
            available_dates = get_weekdays(date_range['start_date'], date_range['end_date'])
            all_available_dates.extend(available_dates)
        all_available_dates = sorted(list(set(all_available_dates)))  # Remove duplicates and sort

        # 3) Build constraints for single GA run
        constraints = {
            'available_dates': all_available_dates,
            'existing_exams': all_existing_exams + locked_exams,  # Include locked exams in existing_exams
            'exam_date_ranges': exam_date_ranges,
            'exams_to_schedule': global_exams
        }

        # 4) Run GA once for all classes
        all_schedules = run_genetic_algorithm(constraints)
        
        if not all_schedules:
            cursor.close()
            conn.close()
            return "No valid schedules could be generated", 400
        
        # Store all schedules in schedule_options
        cursor.execute("DELETE FROM schedule_options")
        conn.commit()

        # Insert all exams into schedule_options
        for i, schedule in enumerate(all_schedules):
            option_number = i + 1
            # First insert locked exams
            for locked_exam in locked_exams:
                cursor.execute("""
                    INSERT INTO schedule_options 
                    (class_id, module_id, option_number, subject_id, exam_type_id, faculty_id, room_id, exam_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    locked_exam['class_id'], 
                    module_id,
                    option_number,
                    locked_exam['subject_id'], 
                    locked_exam['exam_type_id'], 
                    locked_exam['faculty_id'], 
                    locked_exam['room_id'], 
                    locked_exam['exam_date']
                ))
            
            # Then insert GA-generated exams
            for exam in schedule:
                # Determine room_id based on exam type
                if exam['exam_type_id'] == 1:  # Lab exam
                    room_id = exam['designated_lab_id']
                else:  # Non-lab exam
                    room_id = exam['assigned_room_id']

                cursor.execute("""
                    INSERT INTO schedule_options 
                    (class_id, module_id, option_number, subject_id, exam_type_id, faculty_id, room_id, exam_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    exam['class_id'], 
                    module_id,
                    option_number,
                    exam['subject_id'], 
                    exam['exam_type_id'], 
                    exam['faculty_id'], 
                    room_id, 
                    exam['exam_date']
                ))

        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('select_schedules'))
        
    except ValueError as e:
        return f"Invalid date format: {str(e)}", 400
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route('/select_schedules')
def select_schedules():
    try:
        # Get department and year from session
        dept_id = session.get('dept_id')
        year_id = session.get('year_id')
        division_id = session.get('division_id')
        
        if not dept_id or not year_id:
            return redirect(url_for('index'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all schedules for the selected department and year
        cursor.execute("""
            SELECT so.*, s.subject_name, et.exam_type_name, f.faculty_name, r.room_number,
                   c.class_id, c.division_id, d.division_name
            FROM schedule_options so
            JOIN subjects s ON so.subject_id = s.subject_id
            JOIN exam_types et ON so.exam_type_id = et.exam_type_id
            JOIN faculty f ON so.faculty_id = f.faculty_id
            JOIN rooms r ON so.room_id = r.room_id
            JOIN classes c ON so.class_id = c.class_id
            JOIN divisions d ON c.division_id = d.division_id
            WHERE c.dept_id = %s AND c.year_id = %s
            ORDER BY so.option_number, so.exam_date
        """, (dept_id, year_id))
        schedules = cursor.fetchall()
        
        # Group schedules by option number and format dates
        formatted_schedules = []
        for option_number in set(s['option_number'] for s in schedules):
            option_schedules = [s for s in schedules if s['option_number'] == option_number]
            for s in option_schedules:
                if isinstance(s['exam_date'], str):
                    s['exam_date'] = datetime.strptime(s['exam_date'], '%Y-%m-%d')
                s['formatted_date'] = s['exam_date'].strftime('%d-%b-%Y')
                s['day'] = s['exam_date'].strftime('%A')
            
            formatted_schedules.append({
                'option_number': option_number,
                'exams': option_schedules
            })
        
        cursor.close()
        conn.close()
        
        return render_template('select_schedules.html', 
                             schedules=formatted_schedules)
        
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route('/select_schedule/<int:option_number>', methods=['POST'])
def select_schedule(option_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insert selected schedule into final_schedule
        cursor.execute("""
            INSERT INTO final_schedule 
            (class_id, module_id, subject_id, exam_type_id, faculty_id, room_id, exam_date)
            SELECT class_id, module_id, subject_id, exam_type_id, faculty_id, room_id, exam_date
            FROM schedule_options
            WHERE option_number = %s
        """, (option_number,))
        
        conn.commit()
        flash('Schedule selected successfully!', 'success')
        return redirect(url_for('show_schedules'))
        
    except Exception as e:
        conn.rollback()
        flash(f'Error selecting schedule: {str(e)}', 'error')
        return redirect(url_for('select_schedules'))
    finally:
        cursor.close()
        conn.close()

@app.route('/schedules')
def show_schedules():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get all selected schedules grouped by division
        cursor.execute("""
            SELECT DISTINCT c.division_id, dv.division_name
            FROM final_schedule fs
            JOIN classes c ON fs.class_id = c.class_id
            JOIN divisions dv ON c.division_id = dv.division_id
            ORDER BY dv.division_name
        """)
        divisions = cursor.fetchall()
        
        schedules = []
        for division in divisions:
            cursor.execute("""
                SELECT fs.*, s.subject_name, et.exam_type_name, f.faculty_name, r.room_number,
                       d.dept_name, y.year_name, dv.division_name
                FROM final_schedule fs
                JOIN subjects s ON fs.subject_id = s.subject_id
                JOIN exam_types et ON fs.exam_type_id = et.exam_type_id
                JOIN faculty f ON fs.faculty_id = f.faculty_id
                JOIN rooms r ON fs.room_id = r.room_id
                JOIN classes c ON fs.class_id = c.class_id
                JOIN departments d ON c.dept_id = d.dept_id
                JOIN years y ON c.year_id = y.year_id
                JOIN divisions dv ON c.division_id = dv.division_id
                WHERE c.division_id = %s
                ORDER BY fs.exam_date, s.subject_name
            """, (division['division_id'],))
            exams = cursor.fetchall()
            
            if exams:
                # Format dates and add day of week
                for exam in exams:
                    exam['formatted_date'] = exam['exam_date'].strftime('%d-%b-%Y')
                    exam['day'] = exam['exam_date'].strftime('%A')
                
                schedules.append({
                    'option_number': division['division_id'],
                    'division_name': division['division_name'],
                    'exams': exams
                })
        
        # Get all available rooms
        cursor.execute("SELECT room_id, room_number FROM rooms ORDER BY room_number")
        available_rooms = cursor.fetchall()
        
        return render_template('schedules.html', 
                             schedules=schedules, 
                             available_rooms=available_rooms)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/update_schedule', methods=['POST'])
def update_schedule():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    form = request.form.to_dict()
    conflicts = []

    try:
        # Process each edited exam
        for key, new_date in form.items():
            if not key.startswith('exam_date_'):
                continue
            sched_id = key.split('_')[2]
            new_room = form.get(f'room_id_{sched_id}')

            # Fetch the existing exam record
            cursor.execute("""
                SELECT schedule_id, class_id, faculty_id, subject_id
                FROM final_schedule
                WHERE schedule_id = %s
            """, (sched_id,))
            exam = cursor.fetchone()
            if not exam:
                conflicts.append(f"⚠️ Schedule ID {sched_id} not found.")
                continue

            # Check conflicts in master_schedule
            cursor.execute("""
                SELECT 
                  'master' AS src,
                  ms.class_id, ms.faculty_id, ms.room_id, ms.exam_date,
                  d.dept_name, y.year_name, dv.division_name, s.subject_name
                FROM master_schedule ms
                JOIN classes c ON ms.class_id = c.class_id
                JOIN departments d ON c.dept_id = d.dept_id
                JOIN years y ON c.year_id = y.year_id
                JOIN divisions dv ON c.division_id = dv.division_id
                JOIN subjects s ON ms.subject_id = s.subject_id
                WHERE ms.exam_date = %s
                  AND (ms.faculty_id = %s OR ms.room_id = %s OR ms.class_id = %s)
            """, (new_date, exam['faculty_id'], new_room, exam['class_id']))
            master_conflicts = cursor.fetchall()

            # Check conflicts in final_schedule (excluding itself)
            cursor.execute("""
                SELECT 
                  'final' AS src,
                  fs.class_id, fs.faculty_id, fs.room_id, fs.exam_date,
                  d.dept_name, y.year_name, dv.division_name, s.subject_name
                FROM final_schedule fs
                JOIN classes c ON fs.class_id = c.class_id
                JOIN departments d ON c.dept_id = d.dept_id
                JOIN years y ON c.year_id = y.year_id
                JOIN divisions dv ON c.division_id = dv.division_id
                JOIN subjects s ON fs.subject_id = s.subject_id
                WHERE fs.schedule_id != %s
                  AND fs.exam_date = %s
                  AND (fs.faculty_id = %s OR fs.room_id = %s OR fs.class_id = %s)
            """, (sched_id, new_date, exam['faculty_id'], new_room, exam['class_id']))
            final_conflicts = cursor.fetchall()

            # Combine and report
            for c in master_conflicts + final_conflicts:
                date_str = c['exam_date'].strftime('%Y-%m-%d')
                reason_parts = []
                if str(c['room_id']) == str(new_room):
                    reason_parts.append("room")
                if str(c['faculty_id']) == str(exam['faculty_id']):
                    reason_parts.append("faculty")
                if str(c['class_id']) == str(exam['class_id']):
                    reason_parts.append("class")
                reason = " & ".join(reason_parts).title() + " conflict"
                dept = f"{c['dept_name']} {c['year_name']} {c['division_name']}"
                conflicts.append(
                    f"⚠️ {reason} on {date_str}: '{c['subject_name']}' in {dept} "
                    f"uses faculty #{c['faculty_id']} or room #{c['room_id']}."
                )

            # If no conflict for this row, queue the update
            if not master_conflicts and not final_conflicts:
                cursor.execute("""
                    UPDATE final_schedule
                       SET exam_date = %s, room_id = %s
                     WHERE schedule_id = %s
                """, (new_date, new_room, sched_id))

        # Finalize
        if conflicts:
            conn.rollback()
            flash(f"Cannot update schedule. Found {len(conflicts)} conflict(s):", 'error')
            for msg in conflicts:
                flash(msg, 'warning')
        else:
            conn.commit()
            flash("Schedule updated successfully.", 'success')

    except Exception as e:
        conn.rollback()
        flash(f"Error updating schedule: {e}", 'error')

    finally:
        cursor.close()
        conn.close()
        return redirect(url_for('show_schedules'))

@app.route('/download')
def download_schedule():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # First, get schedule data from final_schedule for Excel file
        cursor.execute("""
            SELECT fs.*, s.subject_code, s.subject_name, et.exam_type_name, f.faculty_name, r.room_number,
                   d.dept_name, y.year_name, dv.division_name
            FROM final_schedule fs
            JOIN subjects s ON fs.subject_id = s.subject_id
            JOIN exam_types et ON fs.exam_type_id = et.exam_type_id
            JOIN faculty f ON fs.faculty_id = f.faculty_id
            JOIN rooms r ON fs.room_id = r.room_id
            JOIN classes c ON fs.class_id = c.class_id
            JOIN departments d ON c.dept_id = d.dept_id
            JOIN years y ON c.year_id = y.year_id
            JOIN divisions dv ON c.division_id = dv.division_id
            ORDER BY dv.division_name, fs.exam_date, s.subject_name
        """)
        schedule_data = cursor.fetchall()

        if not schedule_data:
            return "No schedule data available", 404

        # Extract semester from session
        semester = session.get('semester', 'Not Provided')

        # Determine Academic Year based on end date
        latest_exam_date = max([exam['exam_date'] for exam in schedule_data])
        year = latest_exam_date.year
        month = latest_exam_date.month

        if month < 8:  # Before August -> Previous Year - Current Year
            academic_year = f"{year-1}-{year}"
        else:  # After August -> Current Year - Next Year
            academic_year = f"{year}-{year+1}"

        # Convert data into DataFrame for Excel
        df = pd.DataFrame(schedule_data)
        
        # Create a list to store DataFrames for each division
        division_dfs = []
        
        # Group by division and create separate DataFrames
        for division in df['division_name'].unique():
            div_df = df[df['division_name'] == division].copy()
            div_df = div_df.sort_values(['exam_date', 'subject_name'])
            
            # Add division header
            header_df = pd.DataFrame({
                'Academic Year': [academic_year],
                'Semester': [semester],
                'Branch': [div_df['dept_name'].iloc[0]],
                'Year': [div_df['year_name'].iloc[0]],
                'Division': [division],
                'Subject code': [''],
                'Subject Name': [''],
                'Type of Examination': [''],
                'Day': [''],
                'Date': [''],
                'Time': [''],
                'Venue': [''],
                'Examiners': ['']
            })
            
            # Create the division's schedule DataFrame
            schedule_df = pd.DataFrame({
                'Academic Year': [academic_year] * len(div_df),
                'Semester': [semester] * len(div_df),
                'Branch': div_df['dept_name'],
                'Year': div_df['year_name'],
                'Division': div_df['division_name'],
                'Subject code': div_df['subject_code'],
                'Subject Name': div_df['subject_name'],
                'Type of Examination': div_df['exam_type_name'] + ' Exam',
                'Day': div_df['exam_date'].apply(lambda x: calendar.day_name[x.weekday()]),
                'Date': div_df['exam_date'].apply(lambda x: x.strftime('%d-%b-%y')),
                'Time': ['10 to 6'] * len(div_df),
                'Venue': div_df['room_number'],
                'Examiners': div_df['faculty_name']
            })
            
            # Combine header and schedule
            division_dfs.append(pd.concat([header_df, schedule_df]))
        
        # Combine all division DataFrames
        output_df = pd.concat(division_dfs, ignore_index=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            output_df.to_excel(writer, sheet_name='Exam Schedule', index=False)
            
            # Get the workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['Exam Schedule']
            
            # Add some formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1
            })
            
            # Format the headers
            for col_num, value in enumerate(output_df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)  # Set column width
            
            # Add borders to all cells
            border_format = workbook.add_format({'border': 1})
            worksheet.conditional_format(0, 0, len(output_df), len(output_df.columns)-1, {
                'type': 'no_blanks',
                'format': border_format
            })
            
            # Add alternating row colors
            worksheet.conditional_format(1, 0, len(output_df), len(output_df.columns)-1, {
                'type': 'formula',
                'criteria': '=MOD(ROW(),2)=0',
                'format': workbook.add_format({'bg_color': '#F2F2F2'})
            })
        
        output.seek(0)

        # Generate filename based on the scope of the schedule
        if len(df['dept_name'].unique()) == 1:
            dept = df['dept_name'].iloc[0]
            if len(df['year_name'].unique()) == 1:
                year = df['year_name'].iloc[0]
                if len(df['division_name'].unique()) == 1:
                    div = df['division_name'].iloc[0]
                    filename = f"Exam_Schedule_{dept}_{year}_{div}.xlsx"
                else:
                    filename = f"Exam_Schedule_{dept}_{year}_All_Divisions.xlsx"
            else:
                filename = f"Exam_Schedule_{dept}_All_Years.xlsx"
        else:
            filename = "Exam_Schedule_All_Departments.xlsx"

        # Now move data from final_schedule to master_schedule
        cursor.execute("""
            INSERT INTO master_schedule 
            (class_id, module_id, subject_id, exam_type_id, faculty_id, room_id, exam_date)
            SELECT class_id, module_id, subject_id, exam_type_id, faculty_id, room_id, exam_date
            FROM final_schedule
        """)
        
        # Clear final_schedule and schedule_options tables
        cursor.execute("DELETE FROM final_schedule")
        cursor.execute("DELETE FROM schedule_options")
        
        # Clear faculty_preferred_dates table
        cursor.execute("DELETE FROM faculty_preferred_dates")
        
        # Commit all changes
        conn.commit()
        
        # Clear session data
        session.clear()

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        conn.rollback()
        flash(f'Error downloading schedule: {str(e)}', 'error')
        return redirect(url_for('show_schedules'))
    finally:
        cursor.close()
        conn.close()

@app.route('/faculty_preferences')
def faculty_preferences():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get all classes
        cursor.execute("""
            SELECT c.*, d.dept_name, y.year_name, dv.division_name
            FROM classes c
            JOIN departments d ON c.dept_id = d.dept_id
            JOIN years y ON c.year_id = y.year_id
            JOIN divisions dv ON c.division_id = dv.division_id
            ORDER BY d.dept_name, y.year_name, dv.division_name
        """)
        classes = cursor.fetchall()
        
        # Get all exam types
        cursor.execute("SELECT * FROM exam_types ORDER BY exam_type_name")
        exam_types = cursor.fetchall()
        
        # Get existing preferences
        cursor.execute("""
            SELECT fpd.*, f.faculty_name, s.subject_name, et.exam_type_name,
                   d.dept_name, y.year_name, dv.division_name
            FROM faculty_preferred_dates fpd
            JOIN faculty f ON fpd.faculty_id = f.faculty_id
            JOIN subjects s ON fpd.subject_id = s.subject_id
            JOIN exam_types et ON fpd.exam_type_id = et.exam_type_id
            JOIN classes c ON fpd.class_id = c.class_id
            JOIN departments d ON c.dept_id = d.dept_id
            JOIN years y ON c.year_id = y.year_id
            JOIN divisions dv ON c.division_id = dv.division_id
            ORDER BY d.dept_name, y.year_name, dv.division_name, f.faculty_name
        """)
        preferences = cursor.fetchall()
        
        return render_template('faculty_preferences.html',
                             classes=classes,
                             exam_types=exam_types,
                             preferences=preferences)
    finally:
        cursor.close()
        conn.close()

@app.route('/add_preference', methods=['POST'])
def add_preference():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        faculty_id = request.form.get('faculty_id')
        subject_id = request.form.get('subject_id')
        class_id = request.form.get('class_id')
        exam_type_id = request.form.get('exam_type_id')
        preferred_date = request.form.get('preferred_date')
        
        if not all([faculty_id, subject_id, class_id, exam_type_id, preferred_date]):
            flash('All fields are required', 'error')
            return redirect(url_for('faculty_preferences'))
        
        # Check if preference already exists
        cursor.execute("""
            SELECT * FROM faculty_preferred_dates
            WHERE faculty_id = %s AND subject_id = %s AND class_id = %s AND exam_type_id = %s
        """, (faculty_id, subject_id, class_id, exam_type_id))
        if cursor.fetchone():
            flash('Preference already exists for this faculty, subject, class, and exam type combination', 'error')
            return redirect(url_for('faculty_preferences'))
        
        # Add new preference
        cursor.execute("""
            INSERT INTO faculty_preferred_dates (faculty_id, subject_id, class_id, exam_type_id, preferred_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (faculty_id, subject_id, class_id, exam_type_id, preferred_date))
        
        conn.commit()
        flash('Preference added successfully', 'success')
        return redirect(url_for('faculty_preferences'))
    except Exception as e:
        conn.rollback()
        flash(f'Error adding preference: {str(e)}', 'error')
        return redirect(url_for('faculty_preferences'))
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_preference', methods=['POST'])
def delete_preference():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        preference_id = request.form.get('preference_id')
        if not preference_id:
            flash('Invalid preference ID', 'error')
            return redirect(url_for('faculty_preferences'))
        
        cursor.execute("DELETE FROM faculty_preferred_dates WHERE preference_id = %s", (preference_id,))
        conn.commit()
        flash('Preference deleted successfully', 'success')
        return redirect(url_for('faculty_preferences'))
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting preference: {str(e)}', 'error')
        return redirect(url_for('faculty_preferences'))
    finally:
        cursor.close()
        conn.close()

@app.route('/get_faculty_for_class/<int:class_id>')
def get_faculty_for_class(class_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get faculty who teach subjects in this class
        cursor.execute("""
            SELECT DISTINCT f.faculty_id, f.faculty_name
            FROM faculty f
            JOIN subject_class_module scm ON f.faculty_id = scm.faculty_id
            WHERE scm.class_id = %s
            ORDER BY f.faculty_name
        """, (class_id,))
        faculty = cursor.fetchall()
        return jsonify(faculty)
    finally:
        cursor.close()
        conn.close()

@app.route('/get_subjects_for_faculty/<int:class_id>/<int:faculty_id>')
def get_subjects_for_faculty(class_id, faculty_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get subjects taught by this faculty in this class
        cursor.execute("""
            SELECT DISTINCT s.subject_id, s.subject_name
            FROM subjects s
            JOIN subject_class_module scm ON s.subject_id = scm.subject_id
            WHERE scm.class_id = %s AND scm.faculty_id = %s
            ORDER BY s.subject_name
        """, (class_id, faculty_id))
        subjects = cursor.fetchall()
        return jsonify(subjects)
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
