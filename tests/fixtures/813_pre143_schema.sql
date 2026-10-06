-- Frozen from six full-data read-only pg_dump clones on 2026-10-01.
-- Disposable qa640_813_* reconstruction only; guarded by the test loader.

--
-- Name: agent_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.agent_type AS ENUM (
    'LOGON',
    'LORE',
    'GAIA',
    'PSYCHE',
    'MEMNON',
    'MAESTRO',
    'NEMESIS'
);

--
-- Name: emotional_valence; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.emotional_valence AS ENUM (
    '+5|devoted',
    '+4|admiring',
    '+3|trusting',
    '+2|friendly',
    '+1|favorable',
    '0|neutral',
    '-1|wary',
    '-2|disapproving',
    '-3|resentful',
    '-4|hostile',
    '-5|hateful'
);

--
-- Name: entity_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.entity_type AS ENUM (
    'character',
    'faction',
    'place',
    'item'
);

--
-- Name: item_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.item_type AS ENUM (
    'currency',
    'weapon',
    'cybernetic',
    'tech',
    'wearable',
    'consumable',
    'tool',
    'data',
    'artifact'
);

--
-- Name: log_level_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.log_level_type AS ENUM (
    'DEBUG',
    'INFO',
    'WARNING',
    'ERROR',
    'CRITICAL'
);

--
-- Name: relationship_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.relationship_type AS ENUM (
    'family',
    'romantic',
    'friend',
    'companion',
    'ally',
    'contact',
    'pedagogical',
    'professional',
    'authority',
    'rival',
    'enemy',
    'acquaintance',
    'stranger',
    'complex',
    'chosen_kin',
    'comrade',
    'handler',
    'asset',
    'ward',
    'guardian',
    'captor',
    'mentor',
    'patron'
);

--
-- Name: threat_domain_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.threat_domain_type AS ENUM (
    'physical',
    'psychological',
    'social',
    'environmental'
);

--
-- Name: threat_lifecycle_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.threat_lifecycle_type AS ENUM (
    'inception',
    'gestation',
    'manifestation',
    'escalation',
    'culmination',
    'resolution',
    'aftermath'
);

--
-- Name: trait; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.trait AS ENUM (
    'allies',
    'contacts',
    'patron',
    'dependents',
    'status',
    'reputation',
    'resources',
    'domain',
    'enemies',
    'obligations'
);

--
-- Name: FUNCTION set_updated_at(); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.set_updated_at() IS 'BEFORE UPDATE trigger on characters, items, and places (trg_characters_set_updated, trg_items_set_updated, trg_places_set_updated): stamps updated_at with now(), the transaction start time.';

--
-- Name: ai_notebook; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_notebook (
    id bigint NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    log_entry text NOT NULL,
    agent public.agent_type NOT NULL,
    level public.log_level_type DEFAULT 'INFO'::public.log_level_type NOT NULL
);

--
-- Name: TABLE ai_notebook; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ai_notebook IS 'Stores log entries from any internal agent (LORE, GAIA, etc.) for debugging or historical review.';

--
-- Name: ai_notebook_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_notebook_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ai_notebook_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_notebook_id_seq OWNED BY public.ai_notebook.id;

--
-- Name: items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.items (
    id bigint NOT NULL,
    type character varying(100) NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    summary character varying(500) NOT NULL,
    name character varying(50) NOT NULL,
    owner_id bigint,
    history text,
    status character varying(50) DEFAULT 'functional'::character varying NOT NULL,
    extra_data jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: TABLE items; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.items IS 'Physical and digital objects, artifacts, weapons, and significant items tracked in the narrative';

--
-- Name: COLUMN items.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.id IS 'Unique item identifier';

--
-- Name: COLUMN items.type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.type IS 'Category or classification of item (weapon, data, artifact, etc.)';

--
-- Name: COLUMN items.quantity; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.quantity IS 'Number of units if stackable/countable';

--
-- Name: COLUMN items.summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.summary IS 'Brief description of the item';

--
-- Name: COLUMN items.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.name IS 'Item name or designation';

--
-- Name: COLUMN items.owner_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.owner_id IS 'Foreign key to characters.id - current owner/possessor';

--
-- Name: COLUMN items.history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.history IS 'Provenance and past ownership/usage of the item';

--
-- Name: COLUMN items.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.status IS 'Current condition (intact, damaged, active, depleted, etc.)';

--
-- Name: COLUMN items.extra_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.extra_data IS 'JSONB for item-specific properties, abilities, or metadata';

--
-- Name: COLUMN items.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.created_at IS 'When item record was created';

--
-- Name: COLUMN items.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.items.updated_at IS 'Last modification to item record';

--
-- Name: items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.items_id_seq OWNED BY public.items.id;

--
-- Name: ai_notebook id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_notebook ALTER COLUMN id SET DEFAULT nextval('public.ai_notebook_id_seq'::regclass);

--
-- Name: items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items ALTER COLUMN id SET DEFAULT nextval('public.items_id_seq'::regclass);

--
-- Name: ai_notebook ai_notebook_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_notebook
    ADD CONSTRAINT ai_notebook_pkey PRIMARY KEY (id);

--
-- Name: items items_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_name_key UNIQUE (name);

--
-- Name: items items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_pkey PRIMARY KEY (id);

--
-- Name: items trg_items_set_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_items_set_updated BEFORE UPDATE ON public.items FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Name: items items_owner_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_owner_id_fkey1 FOREIGN KEY (owner_id) REFERENCES public.characters(id) ON DELETE SET NULL;
