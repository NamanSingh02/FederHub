BEGIN;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS expected_clients INTEGER DEFAULT 1;

UPDATE job_configurations
SET expected_clients = 1
WHERE expected_clients IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN expected_clients SET NOT NULL;

ALTER TABLE job_configurations
ADD COLUMN IF NOT EXISTS current_round INTEGER DEFAULT 0;

UPDATE job_configurations
SET current_round = 0
WHERE current_round IS NULL;

ALTER TABLE job_configurations
ALTER COLUMN current_round SET NOT NULL;

UPDATE users
SET created_at = CURRENT_TIMESTAMP
WHERE created_at IS NULL;

CREATE TABLE IF NOT EXISTS client_submissions (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES job_configurations(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    client_label VARCHAR NOT NULL,
    round_number INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    accuracy DOUBLE PRECISION,
    loss DOUBLE PRECISION,
    weights_json TEXT NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'accepted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_client_submissions_id
    ON client_submissions(id);

CREATE INDEX IF NOT EXISTS ix_client_submissions_job_round
    ON client_submissions(job_id, round_number);

CREATE UNIQUE INDEX IF NOT EXISTS ux_client_submissions_job_user_round
    ON client_submissions(job_id, user_id, round_number);

COMMIT;
