# Verification: Shadow-Schema Migration Tests on Disposable Databases (#885 B2-6)

## Owner-Sequence Snapshot Bracket

Head `1f70e54d`, rebased on `3e8e692e`.

The audited proof below ran between two read-only snapshots of every public
sequence on `save_02`, `save_05`, and `NEXUS_template`. Each snapshot ran in a
`READ ONLY` transaction:

```
Q="SELECT schemaname, sequencename, last_value FROM pg_sequences WHERE schemaname='public' ORDER BY 1,2"
for db in save_02 save_05 NEXUS_template; do
  psql -X -At -v ON_ERROR_STOP=1 -d $db -c "BEGIN READ ONLY; $Q; COMMIT" > before_$db.txt   # after_$db.txt for the second pass
  md5 -q before_$db.txt
done
```

The md5 is over the psql output (the `BEGIN` and `COMMIT` tags plus 48
`schema|sequence|last_value` rows per database).

| Database | Before | After |
| --- | --- | --- |
| `save_02` | `64b1a40d2587a91f94ab1d114f2fcdab` | `64b1a40d2587a91f94ab1d114f2fcdab` |
| `save_05` | `cd490177df0ae132a741f58bd3ccb016` | `cd490177df0ae132a741f58bd3ccb016` |
| `NEXUS_template` | `6279441154d15a9d08563f036952b0eb` | `6279441154d15a9d08563f036952b0eb` |

`cmp` reported each before and after pair identical.

## Audited Gate

Head `1f70e54d`, rebased on `3e8e692e`.

Gateway variables unset (`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL`):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit \
    tests/test_orrery/test_backstory_secrets_migration_pg.py \
    tests/test_orrery/test_court_patron_migration_pg.py \
    tests/test_orrery/test_distortion_migration_pg.py \
    tests/test_orrery/test_polymorphic_patron_migration_pg.py \
    tests/test_orrery/test_pursue_romance_migration_pg.py \
    tests/test_orrery/test_recruit_ally_migration_pg.py \
    tests/test_orrery/test_seek_redemption_migration_pg.py \
    tests/test_orrery/test_valence_float_migration_pg.py \
    tests/test_orrery/test_build_venture_migration_pg.py \
    tests/test_orrery/test_claim_accounts_migration_pg.py \
    tests/test_orrery/test_mood_migration_pg.py \
    tests/test_orrery/test_geo_resolver_live.py \
    tests/test_orrery/test_weather_migration_pg.py \
    tests/test_dbname_audit.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_geo_resolver_*, qa640_mig077_*, qa640_mig084_*, qa640_mig085_*, qa640_mig086_*, qa640_mig087_*, qa640_mig088_*, qa640_mig090_*, qa640_mig091_*, qa640_mig092_*, qa640_mig095_*, qa640_mig096_*, qa640_weather_migration_*
dbname audit: owner targets: none
48 passed, 5 warnings in 8.61s
```

Exit status 0.
