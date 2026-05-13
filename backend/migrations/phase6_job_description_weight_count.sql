BEGIN;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS weight_count INTEGER DEFAULT 1;

UPDATE job_configurations
SET weight_count = 1
WHERE weight_count IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN weight_count SET NOT NULL;

COMMIT;
