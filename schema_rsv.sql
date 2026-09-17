-- One row per visit (static, written once)
CREATE TABLE visits (
    time              DATE NOT NULL,
    s_ra              DOUBLE PRECISION,
    s_dec             DOUBLE PRECISION,
    rubin_rot_sky_pos DOUBLE PRECISION,
    band              CHAR,
    execution_status  TEXT
);

CREATE INDEX idx_visits_time ON visits(time);