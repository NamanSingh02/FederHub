BEGIN;

CREATE TABLE IF NOT EXISTS round_metrics (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES job_configurations(id),
    round_number INTEGER NOT NULL,
    accuracy DOUBLE PRECISION,
    loss DOUBLE PRECISION,
    num_clients INTEGER,
    total_samples INTEGER,
    global_weights_snapshot TEXT,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_round_metrics_id ON round_metrics(id);
CREATE INDEX IF NOT EXISTS ix_round_metrics_job_round
    ON round_metrics(job_id, round_number);

COMMIT;
