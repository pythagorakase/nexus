-- 066_signal_event_vocab.sql
--
-- Register the two gate-consumed event types that no writer could legally
-- emit (world_events FKs event_types.type): compliance_alert and
-- encoded_message. With these seeded, branch signal emissions (spec idea 7:
-- lighting up the dormant trigger events) can turn the dead gate arms into
-- live package-to-package chains. threat_issued and faction_realignment
-- already exist in the vocabulary.

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'compliance_alert',
        'intelligence',
        'moderate',
        'The subject has reason to believe surveillance or enforcement attention is closing in on them. Consumed by evasion/warning gates; emitted as a signal by detectable surveillance branches.'
    ),
    (
        'encoded_message',
        'interpersonal',
        'minor',
        'A covert communication reached the target through indirect channels. Consumed by obligation gates; emitted as a signal by distanced informant overtures.'
    )
ON CONFLICT (type) DO NOTHING;
