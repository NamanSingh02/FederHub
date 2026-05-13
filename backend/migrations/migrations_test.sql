SELECT column_name
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;


SELECT column_name
FROM information_schema.columns
WHERE table_name = 'job_configurations'
ORDER BY ordinal_position;


SELECT id, email, role, status FROM users;