-- SQL script to create the feedback table
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    session_id INTEGER,
    student_id VARCHAR(20),
    subject VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (session_id) REFERENCES sit_ins(id),
    FOREIGN KEY (student_id) REFERENCES students(idno)
); 