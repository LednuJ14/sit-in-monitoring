-- Database Schema for Sit-in Monitoring System

-- Drop existing tables if they exist
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS announcements;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS sit_ins;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS students;

-- Students Table
CREATE TABLE students (
    idno VARCHAR(20) PRIMARY KEY,
    firstname VARCHAR(50) NOT NULL,
    lastname VARCHAR(50) NOT NULL,
    middlename VARCHAR(50),
    course VARCHAR(20) NOT NULL CHECK (course IN ('BSIT', 'BSCS', 'BSBA', 'BSA', 'BSHM', 'BSE', 'BSCJ')),
    yearlevel INT NOT NULL CHECK (yearlevel BETWEEN 1 AND 5),
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    remaining_sessions INT DEFAULT 30,
    points INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE students ADD points INT DEFAULT 0;

-- Sit-ins Table (Lab usage records)
CREATE TABLE sit_ins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    lab_room VARCHAR(50) NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL DEFAULT NULL,
    created_by VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    admin_notes TEXT NULL, -- Optional notes from admin about approval/rejection
    FOREIGN KEY (student_id) REFERENCES students(idno) ON DELETE CASCADE
);

-- Feedback Table
CREATE TABLE feedback (
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

-- Announcements Table
CREATE TABLE announcements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    visibility VARCHAR(20) NOT NULL CHECK (visibility IN ('all', 'bsit', 'bscs')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expiry_date DATE NULL,
    created_by VARCHAR(50) NOT NULL
);

-- Notifications Table
CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    type VARCHAR(50) NOT NULL, -- e.g., 'reservation', 'system', 'announcement'
    message TEXT NOT NULL,
    reference_id INT NULL, -- Optional reference to sit_in ID or other related record
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (student_id) REFERENCES students(idno) ON DELETE CASCADE
);

-- Insert sample students
INSERT INTO students (idno, firstname, lastname, middlename, course, yearlevel, email, password, remaining_sessions, points) VALUES
('123', 'John', 'Doe', '', 'BSIT', 2, 'john.doe@example.com', '123', 30, 0),
('111', 'Jane', 'Smith', 'Marie', 'BSCJ', 3, 'jane.smith@example.com', '111', 15, 0),
('20230003', 'Robert', 'Johnson', '', 'BSIT', 1, 'robert.johnson@example.com', 'password123', 30, 0),
('20230004', 'Emily', 'Williams', 'Grace', 'BSCS', 2, 'emily.williams@example.com', 'password123', 30, 0),
('20230005', 'Michael', 'Brown', '', 'BSIT', 4, 'michael.brown@example.com', 'password123', 30, 0),
('22629828', 'Test', 'Student', '', 'BSIT', 3, 'test.student@example.com', 'password123', 30, 0);

-- Insert sample sit-ins
INSERT INTO sit_ins (student_id, purpose, lab_room, start_time, created_by) VALUES
('123', 'C', '524', NOW(), 'admin'),
('111', 'C', '526', NOW(), 'admin'),
('20230003', 'C', '528', NOW(), 'admin'),
('20230004', 'C', '544', NOW(), 'admin'),
('20230005', 'C', '542', NOW(), 'admin');

-- Insert sample feedback
INSERT INTO feedback (student_id, subject, message, created_at, response, response_date) VALUES
('2023-0001', 'Lab Equipment Issue', 'Some computers in Laboratory 1 are not working properly.', DATE_SUB(NOW(), INTERVAL 3 DAY), 'Thank you for reporting this issue. We will look into it immediately.', DATE_SUB(NOW(), INTERVAL 2 DAY)),
('2023-0002', 'Suggestion for Lab Hours', 'It would be helpful if the labs could be open for longer hours during exam week.', DATE_SUB(NOW(), INTERVAL 2 DAY), NULL, NULL),
('2023-0003', 'Air Conditioning Problem', 'The air conditioning in Laboratory 3 is too cold.', DATE_SUB(NOW(), INTERVAL 1 DAY), 'We have adjusted the temperature. Please let us know if it is better now.', DATE_SUB(NOW(), INTERVAL 12 HOUR)),
('2023-0004', 'Internet Connectivity', 'The internet connection in Laboratory 2 is very slow.', NOW(), NULL, NULL),
('2023-0005', 'Positive Feedback', 'I really appreciate the new computer upgrades in Laboratory 4. They work much faster now!', DATE_SUB(NOW(), INTERVAL 5 DAY), 'We are glad to hear that you find the upgrades helpful!', DATE_SUB(NOW(), INTERVAL 4 DAY));

-- Insert sample announcements
INSERT INTO announcements (title, content, visibility, created_at, expiry_date, created_by) VALUES
('Lab Maintenance Schedule', 'All laboratories will be closed for maintenance on Saturday, October 7, 2023, from 8:00 AM to 5:00 PM. Please plan your sit-in sessions accordingly.', 'all', DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_ADD(NOW(), INTERVAL 2 DAY), 'admin'),
('Special Workshop for BSIT Students', 'A special workshop on Web Development will be held on October 10, 2023, in Laboratory 1. All BSIT students are encouraged to attend.', 'bsit', DATE_SUB(NOW(), INTERVAL 3 DAY), DATE_ADD(NOW(), INTERVAL 5 DAY), 'admin'),
('Extended Lab Hours', 'During the upcoming midterm exam week, all laboratories will be open until 10:00 PM. Take advantage of the extended hours for your projects and study sessions.', 'all', DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_ADD(NOW(), INTERVAL 7 DAY), 'admin'),
('New Software Installation', 'New programming software has been installed in all laboratories. BSCS students can now use the latest version of Visual Studio Code and other development tools.', 'bscs', NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY), 'admin');

-- Create indexes for better performance
CREATE INDEX idx_sit_ins_student_id ON sit_ins(student_id);
CREATE INDEX idx_sit_ins_start_time ON sit_ins(start_time);
CREATE INDEX idx_sit_ins_end_time ON sit_ins(end_time);
CREATE INDEX idx_feedback_student_id ON feedback(student_id);
CREATE INDEX idx_feedback_created_at ON feedback(created_at);
CREATE INDEX idx_announcements_visibility ON announcements(visibility);
CREATE INDEX idx_announcements_expiry_date ON announcements(expiry_date);

-- Update remaining sessions based on usage
UPDATE students s
SET remaining_sessions = CASE 
    WHEN s.course IN ('BSIT', 'BSCS') THEN 30 - (SELECT COUNT(*) FROM sit_ins WHERE student_id = s.idno)
    ELSE 15 - (SELECT COUNT(*) FROM sit_ins WHERE student_id = s.idno)
END; 