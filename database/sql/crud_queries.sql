USE traffic_db;

-- READ 1: average traffic by weather type, busiest first (join across 3 tables)
SELECT wc.weather_main, ROUND(AVG(t.traffic_volume)) AS avg_traffic, COUNT(*) AS n
FROM traffic_observations t
JOIN weather_readings r ON r.obs_id = t.obs_id
JOIN weather_conditions wc ON wc.condition_id = r.condition_id
GROUP BY wc.weather_main
ORDER BY avg_traffic DESC;

-- READ 2: holiday vs normal day traffic
SELECT COALESCE(h.holiday_name, 'Not a holiday') AS day_type,
       ROUND(AVG(t.traffic_volume)) AS avg_traffic
FROM traffic_observations t
LEFT JOIN holidays h ON h.holiday_id = t.holiday_id
GROUP BY day_type
ORDER BY avg_traffic DESC;

-- READ 3: busiest hours of the day
SELECT HOUR(date_time) AS hour_of_day, ROUND(AVG(traffic_volume)) AS avg_traffic
FROM traffic_observations
GROUP BY hour_of_day
ORDER BY avg_traffic DESC
LIMIT 5;

-- CREATE: add a new observation and its weather reading
INSERT INTO traffic_observations (date_time, traffic_volume, holiday_id)
VALUES ('2018-10-01 00:00:00', 450, NULL);
INSERT INTO weather_readings (obs_id, condition_id, temp_k, rain_1h, snow_1h, clouds_all)
VALUES (LAST_INSERT_ID(), 1, 285.50, 0, 0, 20);

-- UPDATE: correct the traffic volume of that observation
UPDATE traffic_observations SET traffic_volume = 475
WHERE date_time = '2018-10-01 00:00:00';

-- READ back to prove the update
SELECT * FROM traffic_observations WHERE date_time = '2018-10-01 00:00:00';

-- DELETE: remove the weather reading first, then the observation
DELETE FROM weather_readings
WHERE obs_id = (SELECT obs_id FROM traffic_observations
                WHERE date_time = '2018-10-01 00:00:00');

DELETE FROM traffic_observations
WHERE date_time = '2018-10-01 00:00:00';

-- Confirm it's gone (should return 0)
SELECT COUNT(*) FROM traffic_observations
WHERE date_time = '2018-10-01 00:00:00';
