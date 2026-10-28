-- Create the database
CREATE DATABASE IF NOT EXISTS traffic_db;

-- Select the database
USE traffic_db;


-- Holidays table
CREATE TABLE holidays (
    holiday_id INT AUTO_INCREMENT PRIMARY KEY,
    holiday_name VARCHAR(50) NOT NULL UNIQUE
);


-- Weather conditions table
CREATE TABLE weather_conditions (
    condition_id INT AUTO_INCREMENT PRIMARY KEY,
    weather_main VARCHAR(30) NOT NULL,
    weather_description VARCHAR(255) NOT NULL,
    UNIQUE (weather_main, weather_description)
);


-- Traffic observations table
CREATE TABLE traffic_observations (
    obs_id INT AUTO_INCREMENT PRIMARY KEY,
    date_time DATETIME NOT NULL UNIQUE,
    traffic_volume INT NOT NULL,
    holiday_id INT,
    FOREIGN KEY (holiday_id) REFERENCES holidays(holiday_id)
);


-- Weather readings table
CREATE TABLE weather_readings (
    reading_id INT AUTO_INCREMENT PRIMARY KEY,
    obs_id INT NOT NULL,
    condition_id INT NOT NULL,
    temp_k DECIMAL(6,2),
    rain_1h DECIMAL(7,2),
    snow_1h DECIMAL(5,2),
    clouds_all INT,
    FOREIGN KEY (obs_id) REFERENCES traffic_observations(obs_id),
    FOREIGN KEY (condition_id) REFERENCES weather_conditions(condition_id)
);
