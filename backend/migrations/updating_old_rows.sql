UPDATE job_configurations
SET created_at = NOW()
WHERE created_at IS NULL;