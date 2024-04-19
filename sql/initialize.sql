-- initialize.sql
-- Initializes the OpenParcel database.
--
-- Nathan Campos <nathan@innoveworkshop.com>

-- Ensure we have our database.
CREATE DATABASE IF NOT EXISTS openparcel;
USE openparcel;

-- Users table.
CREATE TABLE IF NOT EXISTS users(
	id              BIGINT          PRIMARY KEY AUTO_INCREMENT,
	username        VARCHAR(30)     NOT NULL,
	password        CHAR(64)        NOT NULL,
	salt            CHAR(32)        NOT NULL,
    access_level    TINYINT         NOT NULL    DEFAULT 10,

    CONSTRAINT un_username UNIQUE (username)
) ENGINE = INNODB;

-- User application authentication tokens.
CREATE TABLE IF NOT EXISTS auth_tokens(
	token           CHAR(40)        PRIMARY KEY NOT NULL,
	user_id         BIGINT          NOT NULL,
	description     VARCHAR(150)    NOT NULL,
	active          BOOLEAN         NOT NULL    DEFAULT TRUE,

	CONSTRAINT fk_token_user FOREIGN KEY (user_id) REFERENCES users(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE
) ENGINE = INNODB;

-- Tracked parcels. Maintains a list of all the parcels tracked by the system.
CREATE TABLE IF NOT EXISTS parcels(
	id              BIGINT          PRIMARY KEY AUTO_INCREMENT,
	carrier         VARCHAR(50)     NOT NULL,
	tracking_code   VARCHAR(255)    NOT NULL,
    slug            VARCHAR(50)     NOT NULL,
	created         DATETIME        NOT NULL    DEFAULT CURRENT_TIMESTAMP
) ENGINE = INNODB;
CREATE INDEX idx_parcels_carrier_tracking ON parcels(carrier, tracking_code);
CREATE UNIQUE INDEX idx_parcels_slug ON parcels(slug);

-- Relationship table for a user's tracked parcels.
CREATE TABLE IF NOT EXISTS user_parcels(
	name        VARCHAR(100)    NOT NULL,
	archived    BOOLEAN         NOT NULL    DEFAULT FALSE,
	user_id     BIGINT,
	parcel_id   BIGINT,

	PRIMARY KEY (user_id, parcel_id),

	CONSTRAINT fk_user_parcels_user FOREIGN KEY (user_id) REFERENCES users(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE,
	CONSTRAINT fk_user_parcels_parcel FOREIGN KEY (parcel_id) REFERENCES parcels(id)
		ON UPDATE CASCADE
		ON DELETE RESTRICT
) ENGINE = INNODB;

-- Tracking history cache.
CREATE TABLE IF NOT EXISTS history_cache(
	id          BIGINT      PRIMARY KEY AUTO_INCREMENT,
	parcel_id   BIGINT      NOT NULL,
	retrieved   DATETIME    NOT NULL    DEFAULT CURRENT_TIMESTAMP,
	data        JSON        NOT NULL,

	CONSTRAINT fk_history_parcel FOREIGN KEY (parcel_id) REFERENCES parcels(id)
		ON UPDATE CASCADE
		ON DELETE CASCADE
) ENGINE = INNODB;
CREATE INDEX idx_history_retrieved ON history_cache(retrieved);

-- Proxy list.
CREATE TABLE IF NOT EXISTS proxies(
    id          BIGINT          PRIMARY KEY AUTO_INCREMENT,
    addr        VARCHAR(15)     NOT NULL,
    port        SMALLINT        NOT NULL,
    country     VARCHAR(2)      NOT NULL,
    speed       MEDIUMINT       NOT NULL,
    protocol    VARCHAR(6)      NOT NULL,
    active      BOOLEAN         NOT NULL    DEFAULT TRUE,
    carriers    JSON            NOT NULL
) ENGINE = INNODB;
CREATE INDEX idx_proxies_country ON proxies(country);
CREATE INDEX idx_proxies_speed ON proxies(speed);
