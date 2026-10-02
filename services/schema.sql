CREATE TABLE IF NOT EXISTS crop_lots (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 crop TEXT NOT NULL, market TEXT NOT NULL, grade TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS disease_assessments (
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES crop_lots(id) ON DELETE CASCADE,
 image_path TEXT NOT NULL, label TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 severity TEXT NOT NULL, storage_compromised INTEGER NOT NULL DEFAULT 0,
 model_version TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS market_decisions (
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES crop_lots(id) ON DELETE CASCADE,
 disease_id INTEGER REFERENCES disease_assessments(id) ON DELETE SET NULL, input_json TEXT NOT NULL,
 result_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS holding_positions (
 lot_id INTEGER PRIMARY KEY REFERENCES crop_lots(id) ON DELETE CASCADE,
 reference_price REAL NOT NULL, stop_loss_price REAL NOT NULL, remaining_quintals REAL NOT NULL,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crop_alerts (
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES crop_lots(id) ON DELETE CASCADE,
 decision_id INTEGER NOT NULL REFERENCES market_decisions(id), message TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS disease_lot_time ON disease_assessments(lot_id, created_at);
CREATE TABLE IF NOT EXISTS market_prices (
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES crop_lots(id) ON DELETE CASCADE,
 price_date TEXT NOT NULL, modal_price REAL NOT NULL CHECK(modal_price>0),
 source TEXT NOT NULL, fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(lot_id,price_date)
);
CREATE TABLE IF NOT EXISTS monitor_runs (
 id INTEGER PRIMARY KEY CHECK(id=1), last_run TEXT, status TEXT NOT NULL DEFAULT 'not_started',
 details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS alert_events (
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES crop_lots(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, event_key TEXT NOT NULL UNIQUE, message TEXT NOT NULL,
 price REAL, acknowledged_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS alert_events_lot ON alert_events(lot_id,id);
CREATE TABLE IF NOT EXISTS monitor_leases (
 id INTEGER PRIMARY KEY CHECK(id=1), expires_at REAL NOT NULL DEFAULT 0
);
