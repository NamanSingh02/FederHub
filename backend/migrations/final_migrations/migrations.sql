BEGIN;

CREATE TABLE IF NOT EXISTS job_assignments (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES job_configurations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_job_assignments_job_id
    ON job_assignments(job_id);

CREATE INDEX IF NOT EXISTS ix_job_assignments_user_id
    ON job_assignments(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_job_assignments_job_user
    ON job_assignments(job_id, user_id);

COMMIT;
