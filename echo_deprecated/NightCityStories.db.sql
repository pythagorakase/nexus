-- -------------------------------------------------------------
-- TablePlus 6.4.2(600)
--
-- https://tableplus.com/
--
-- Database: NightCityStories.db
-- Generation Time: 2025-03-30 10:04:20.8260
-- -------------------------------------------------------------


CREATE TABLE character_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character1_id INTEGER,
            character2_id INTEGER,
            dynamic TEXT,
            asymmetry TEXT,
            recent_events TEXT,
            FOREIGN KEY(character1_id) REFERENCES characters(id),
            FOREIGN KEY(character2_id) REFERENCES characters(id)
        );

CREATE TABLE characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            aliases TEXT,
            description TEXT,
            appearance TEXT,
            background TEXT,
            personality TEXT,
            conflicts TEXT,
            internal_conflicts TEXT,
            unspoken_desires TEXT,
            evolution TEXT,
            status TEXT,
            dialog TEXT
        );

CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            title TEXT,
            arc_id TEXT,
            description TEXT,
            cause TEXT,
            consequences TEXT,
            characters_involved TEXT,
            episodes TEXT,
            conflicts_triggered TEXT,
            status TEXT,
            key_dialogue TEXT,
            FOREIGN KEY(arc_id) REFERENCES story_arcs(arc_id)
        );

CREATE TABLE locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            type TEXT,
            description TEXT,
            geographical_position TEXT,
            inhabitants TEXT,
            status TEXT,
            historical_significance TEXT,
            associated_story_arcs TEXT,
            secrets TEXT,
            security_measures TEXT,
            key_dialogue TEXT
        );

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE story_arcs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arc_id TEXT UNIQUE,
            title TEXT,
            description TEXT,
            themes TEXT,
            status TEXT
        );

