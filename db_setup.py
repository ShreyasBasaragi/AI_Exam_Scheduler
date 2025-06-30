import mysql.connector

def main():
    # 1) Connect (adjust credentials as needed)
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='useyourpassword'
    )
    cursor = conn.cursor()

    # 2) Create and switch to our database
    cursor.execute("CREATE DATABASE IF NOT EXISTS ai_exam_scheduler_2;")
    cursor.execute("USE ai_exam_scheduler_2;")

    # 3) Drop tables in reverse‐dependency order
    for tbl in [
        "final_schedule",
        "master_schedule",
        "schedule_options",
        "subject_class_module",
        "subject_labs",
        "subject_exam_types",
        "faculty_preferred_dates",
        "classes",
        "faculty",
        "rooms",
        "modules",
        "exam_types",
        "divisions",
        "years",
        "departments",
        "subjects"
    ]:
        cursor.execute(f"DROP TABLE IF EXISTS {tbl};")

    # 4) Recreate tables with FKs
    cursor.execute("""
    CREATE TABLE departments (
      dept_id INT AUTO_INCREMENT PRIMARY KEY,
      dept_name VARCHAR(50) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE years (
      year_id INT AUTO_INCREMENT PRIMARY KEY,
      year_name VARCHAR(20) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE divisions (
      division_id INT AUTO_INCREMENT PRIMARY KEY,
      division_name VARCHAR(10) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE exam_types (
      exam_type_id INT AUTO_INCREMENT PRIMARY KEY,
      exam_type_name VARCHAR(20) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE modules (
      module_id INT AUTO_INCREMENT PRIMARY KEY,
      module_name VARCHAR(100) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE subjects (
      subject_id INT AUTO_INCREMENT PRIMARY KEY,
      subject_code VARCHAR(20) NOT NULL,
      subject_name VARCHAR(100) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE rooms (
      room_id INT AUTO_INCREMENT PRIMARY KEY,
      room_number VARCHAR(20) NOT NULL UNIQUE,
      is_lab TINYINT(1) DEFAULT 0
    );
    """)
    cursor.execute("""
    CREATE TABLE faculty (
      faculty_id INT PRIMARY KEY,
      faculty_name VARCHAR(100) NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE classes (
      class_id INT AUTO_INCREMENT PRIMARY KEY,
      dept_id INT NOT NULL,
      year_id INT NOT NULL,
      division_id INT NOT NULL,
      assigned_room_id INT,
      FOREIGN KEY (dept_id) REFERENCES departments(dept_id),
      FOREIGN KEY (year_id) REFERENCES years(year_id),
      FOREIGN KEY (division_id) REFERENCES divisions(division_id),
      FOREIGN KEY (assigned_room_id) REFERENCES rooms(room_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE faculty_preferred_dates (
      preference_id INT AUTO_INCREMENT PRIMARY KEY,
      faculty_id INT NOT NULL,
      subject_id INT NOT NULL,
      class_id INT NOT NULL,
      exam_type_id INT NOT NULL,
      preferred_date DATE NOT NULL,
      FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id),
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (class_id) REFERENCES classes(class_id),
      FOREIGN KEY (exam_type_id) REFERENCES exam_types(exam_type_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE subject_exam_types (
      set_id INT AUTO_INCREMENT PRIMARY KEY,
      subject_id INT NOT NULL,
      exam_type_id INT NOT NULL,
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (exam_type_id) REFERENCES exam_types(exam_type_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE subject_labs (
      subject_lab_id INT AUTO_INCREMENT PRIMARY KEY,
      subject_id INT NOT NULL,
      room_id INT NOT NULL,
      class_id INT NOT NULL,
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (room_id) REFERENCES rooms(room_id),
      FOREIGN KEY (class_id) REFERENCES classes(class_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE subject_class_module (
      id INT AUTO_INCREMENT PRIMARY KEY,
      class_id INT NOT NULL,
      module_id INT NOT NULL,
      subject_id INT NOT NULL,
      faculty_id INT NOT NULL,
      FOREIGN KEY (class_id) REFERENCES classes(class_id),
      FOREIGN KEY (module_id) REFERENCES modules(module_id),
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE schedule_options (
      schedule_option_id INT AUTO_INCREMENT PRIMARY KEY,
      class_id INT NOT NULL,
      module_id INT NOT NULL,
      option_number INT NOT NULL,
      subject_id INT NOT NULL,
      exam_type_id INT NOT NULL,
      faculty_id INT NOT NULL,
      room_id INT NOT NULL,
      exam_date DATE NOT NULL,
      FOREIGN KEY (class_id) REFERENCES classes(class_id),
      FOREIGN KEY (module_id) REFERENCES modules(module_id),
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (exam_type_id) REFERENCES exam_types(exam_type_id),
      FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id),
      FOREIGN KEY (room_id) REFERENCES rooms(room_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE master_schedule (
      schedule_id INT AUTO_INCREMENT PRIMARY KEY,
      class_id INT NOT NULL,
      module_id INT NOT NULL,
      subject_id INT NOT NULL,
      exam_type_id INT NOT NULL,
      faculty_id INT NOT NULL,
      room_id INT NOT NULL,
      exam_date DATE NOT NULL,
      FOREIGN KEY (class_id) REFERENCES classes(class_id),
      FOREIGN KEY (module_id) REFERENCES modules(module_id),
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (exam_type_id) REFERENCES exam_types(exam_type_id),
      FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id),
      FOREIGN KEY (room_id) REFERENCES rooms(room_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE final_schedule (
      schedule_id INT AUTO_INCREMENT PRIMARY KEY,
      class_id INT NOT NULL,
      module_id INT NOT NULL,
      subject_id INT NOT NULL,
      exam_type_id INT NOT NULL,
      faculty_id INT NOT NULL,
      room_id INT NOT NULL,
      exam_date DATE NOT NULL,
      FOREIGN KEY (class_id) REFERENCES classes(class_id),
      FOREIGN KEY (module_id) REFERENCES modules(module_id),
      FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
      FOREIGN KEY (exam_type_id) REFERENCES exam_types(exam_type_id),
      FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id),
      FOREIGN KEY (room_id) REFERENCES rooms(room_id)
    );
    """)

    # 5) Insert your data in FK‐safe order
    cursor.executemany(
        "INSERT INTO departments (dept_id, dept_name) VALUES (%s, %s);",
        [(1, "Computer Engineering")]
    )
    cursor.executemany(
        "INSERT INTO years (year_id, year_name) VALUES (%s, %s);",
        [(1, "Second")]
    )
    cursor.executemany(
        "INSERT INTO divisions (division_id, division_name) VALUES (%s, %s);",
        [(1, "A"), (2, "B")]
    )
    cursor.executemany(
        "INSERT INTO exam_types (exam_type_id, exam_type_name) VALUES (%s, %s);",
        [(1, "lab"), (2, "cp"), (3, "cvv"), (4, "ppt")]
    )
    cursor.executemany(
        "INSERT INTO modules (module_id, module_name) VALUES (%s, %s);",
        [(1, "Module 1"), (2, "Module 2")]
    )
    cursor.executemany(
        "INSERT INTO subjects (subject_id, subject_code, subject_name) VALUES (%s, %s, %s);",
        [
            (1, "CS2065", "Data Structures"),
            (2, "CS2008", "Operating Systems"),
            (3, "CS2245", "Microprocessors & Microcontrollers"),
            (4, "CS2246", "Computer Graphics and Virtual Reality"),
            (5, "CS2247", "Theory of Computation")
        ]
    )
    cursor.executemany(
        "INSERT INTO rooms (room_id, room_number, is_lab) VALUES (%s, %s, %s);",
        [
            (1, "1328", 0),
            (2, "1325", 0),
            (3, "1323D", 1),
            (4, "1323A", 1),
            (5, "1321D", 1),
            (7, "1326",  1),
            (8, "1321A", 1)
        ]
    )
    cursor.executemany(
        "INSERT INTO faculty (faculty_id, faculty_name) VALUES (%s, %s);",
        [
            (10638, "PROF. (SMT.) SANGITA GAUTAM LADE"),
            (10662, "PROF. (SMT.) SARASWATI VIJAYSINGH PATIL"),
            (11069, "PROF. AMOL ASHOK BHILARE"),
            (11639, "PROF. (Dr.) RAKHI JAYKUMAR BHARDWAJ"),
            (11776, "PROF. (Dr.) SONALI MALLINATH ANTAD"),
            (11791, "PROF. (SMT.) SHAILAJA NILESH UKE"),
            (11872, "PROF. ANAND MOHANRAO MAGAR"),
            (11978, "PROF. (Dr.) AARTI AMOD AGARKAR"),
            (12021, "PROF. SANTUSHTI SANTOSH BETGERI")
        ]
    )
    cursor.executemany(
        "INSERT INTO classes (class_id, dept_id, year_id, division_id, assigned_room_id) VALUES (%s, %s, %s, %s, %s);",
        [
            (1, 1, 1, 1, 1),
            (2, 1, 1, 2, 2)
        ]
    )
    cursor.executemany(
        "INSERT INTO subject_exam_types (set_id, subject_id, exam_type_id) VALUES (%s, %s, %s);",
        [
            (1, 1, 1), (2, 1, 2), (3, 1, 3),
            (4, 2, 1), (5, 2, 2), (6, 2, 3),
            (7, 3, 2), (8, 3, 3),
            (10,4, 2), (11,4, 4), (12,4, 3),
            (14,5, 3)
        ]
    )
    cursor.executemany(
        "INSERT INTO subject_labs (subject_lab_id, subject_id, room_id, class_id) VALUES (%s, %s, %s, %s);",
        [
            (1,1,3,1), (2,2,4,1), (3,3,4,1), (4,4,5,1),
            (5,4,7,2), (6,1,8,2), (7,2,4,2), (8,3,3,2)
        ]
    )
    cursor.executemany(
        "INSERT INTO subject_class_module (id, class_id, module_id, subject_id, faculty_id) VALUES (%s, %s, %s, %s, %s);",
        [
            (11,1,2,1,11069), (12,1,2,2,10638), (13,1,2,3,11776),
            (14,1,2,4,11639), (15,1,2,5,11872),
            (16,2,2,1,11069), (17,2,2,2,10662), (18,2,2,3,12021),
            (19,2,2,4,11791), (20,2,2,5,11978)
        ]
    )

    # No initial rows for faculty_preferred_dates, schedule_options, master_schedule, final_schedule

    conn.commit()
    cursor.close()
    conn.close()
    print("Database and data initialized successfully.")

if __name__ == "__main__":
    main()
