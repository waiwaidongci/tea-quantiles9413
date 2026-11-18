Schema v1 is defined by the SQLAlchemy models and created at startup via Base.metadata.create_all. For this local small application no destructive migration is run. Back up named db-data before modifying schemas.

Schema v2 adds the protected-release tables (`protection_policies`, `protected_releases`) and a nullable `audits.study_id`. New tables come from `create_all`; the additive audit column is applied by `src.config.database.ensure_schema()` on startup. No existing rows are rewritten and no column is dropped.
