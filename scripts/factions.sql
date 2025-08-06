DROP TABLE IF EXISTS factions;

CREATE TABLE factions (
    id int8 PRIMARY KEY,
    name varchar(255) NOT NULL UNIQUE,
    summary text,
    ideology text,
    history text,
    current_activity text,
    hidden_agenda text,
    territory text,
    primary_location int8 REFERENCES places(id),
    power_level numeric(3,2) DEFAULT 0.5,
    resources text,
    extra_data jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE faction_relationship_type AS ENUM (
    -- Cooperative
    'alliance', 
    'trade_partners',
    'truce',  
    'vassalage',  
    'coalition',  
    'war', 
    'rivalry',   
    'ideological_enemy',
    'competitor',    
    'splinter',  
    'unknown',   
    'shadow_partner' 
);

CREATE TABLE faction_relationships (
    faction1_id int8 NOT NULL REFERENCES factions(id),
    faction2_id int8 NOT NULL REFERENCES factions(id),
    relationship_type faction_relationship_type NOT NULL,
    current_status text,
    history text,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (faction1_id, faction2_id),
    CHECK (faction1_id < faction2_id)
);

CREATE TYPE faction_member_role AS ENUM (
    'leader',
    'employee',
    'member',
    'target',
    'informant',
    'sympathizer',
    'defector',
    'exile',
    'insider_threat'
);

CREATE TABLE faction_character_relationships (
    faction_id int8 NOT NULL REFERENCES factions(id),
    character_id int8 NOT NULL REFERENCES characters(id),
    role faction_member_role NOT NULL,
    current_status text,
    history text,
    public_knowledge boolean DEFAULT true,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (faction_id, character_id)
);