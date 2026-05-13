BEGIN;

-- =========================
-- USERS TABLE UPGRADES
-- =========================

ALTER TABLE users
ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255);

-- Give any old Phase 1 users a temporary password hash
-- Temporary password for old users: TempPass123!
UPDATE users
SET hashed_password = '$2b$12$7ibPtg5XrEnhuE65tj8lsuoaMdBDqNDdwraaYS1mLbliIV5BhRCk6'
WHERE hashed_password IS NULL;

ALTER TABLE users
ALTER COLUMN hashed_password SET NOT NULL;

ALTER TABLE users
ALTER COLUMN role SET DEFAULT 'ml_engineer';

ALTER TABLE users
ALTER COLUMN status SET DEFAULT 'active';

-- =========================
-- JOB CONFIGURATIONS TABLE UPGRADES
-- =========================

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS round_count INTEGER;

UPDATE job_configurations
SET round_count = 5
WHERE round_count IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN round_count SET DEFAULT 5;

ALTER TABLE job_configurations
ALTER COLUMN round_count SET NOT NULL;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS local_epochs INTEGER;

UPDATE job_configurations
SET local_epochs = 3
WHERE local_epochs IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN local_epochs SET DEFAULT 3;

ALTER TABLE job_configurations
ALTER COLUMN local_epochs SET NOT NULL;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS created_by INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'job_configurations_created_by_fkey'
    ) THEN
        ALTER TABLE job_configurations
        ADD CONSTRAINT job_configurations_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES users(id);
    END IF;
END $$;

COMMIT;