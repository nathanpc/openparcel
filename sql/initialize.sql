--- initialize.sql
--- Initializes the OpenParcel database.
---
--- Nathan Campos <nathan@innoveworkshop.com>

-- Ensure we at least have access to foreign keys.
PRAGMA foreign_keys = ON;

-- Users table.
CREATE TABLE IF NOT EXISTS users(
	id              INTEGER     PRIMARY KEY AUTOINCREMENT,
	username        TEXT        NOT NULL    UNIQUE,
	password        TEXT        NOT NULL,
	salt            TEXT        NOT NULL,
    access_level    INTEGER     NOT NULL    DEFAULT 10
);

-- User application authentication tokens.
CREATE TABLE IF NOT EXISTS auth_tokens(
	token           TEXT        PRIMARY KEY     NOT NULL,
	user_id         INTEGER     NOT NULL,
	description     TEXT        NOT NULL,
	active          BOOLEAN     NOT NULL        DEFAULT TRUE,

	FOREIGN KEY (user_id) REFERENCES users(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE
);

-- Tracked parcels. Maintains a list of all the parcels tracked by the system.
CREATE TABLE IF NOT EXISTS parcels(
	id              INTEGER     PRIMARY KEY AUTOINCREMENT,
	carrier         TEXT        NOT NULL,
	tracking_code   TEXT        NOT NULL,
    slug            TEXT        NOT NULL,
	created         TIMESTAMP   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parcels_carrier
	ON parcels(carrier);
CREATE INDEX IF NOT EXISTS idx_parcels_tracking_code
	ON parcels(tracking_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_parcels_slug
	ON parcels(slug);

-- Relationship table for a user's tracked parcels.
CREATE TABLE IF NOT EXISTS user_parcels(
	name        TEXT        NOT NULL,
	archived    BOOLEAN     NOT NULL    DEFAULT FALSE,
	user_id     INTEGER,
	parcel_id   INTEGER,

	PRIMARY KEY (user_id, parcel_id),

	FOREIGN KEY (user_id) REFERENCES users(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE,
	FOREIGN KEY (parcel_id) REFERENCES parcels(id)
		ON UPDATE CASCADE
		ON DELETE RESTRICT
);

-- Tracking history cache.
CREATE TABLE IF NOT EXISTS history_cache(
	id          INTEGER     PRIMARY KEY AUTOINCREMENT,
	parcel_id   INTEGER     NOT NULL,
	retrieved   TIMESTAMP   NOT NULL    DEFAULT CURRENT_TIMESTAMP,
	data        JSON        NOT NULL,

	FOREIGN KEY (parcel_id) REFERENCES parcels(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE
);

-- Proxy list.
CREATE TABLE IF NOT EXISTS proxies(
    id          INTEGER         PRIMARY KEY AUTOINCREMENT,
    addr        VARCHAR(15)     NOT NULL,
    port        INTEGER         NOT NULL,
    country     VARCHAR(2)      NOT NULL,
    speed       INTEGER         NOT NULL,
    protocol    VARCHAR(6)      NOT NULL,
    active      BOOLEAN         NOT NULL    DEFAULT TRUE,
    carriers    JSON            NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proxies_country
	ON proxies(country);
CREATE INDEX IF NOT EXISTS idx_proxies_speed
	ON proxies(speed);
