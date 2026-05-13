BEGIN;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS results_published INTEGER DEFAULT 0;

UPDATE job_configurations
SET results_published = 0
WHERE results_published IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN results_published SET NOT NULL;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;

COMMIT;
