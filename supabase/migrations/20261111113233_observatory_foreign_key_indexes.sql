-- Cover foreign-key lookups without changing access or evidence semantics.
create index publications_edition_hash on observatory.publications(edition_id,expected_hash);
create index reading_checkpoints_source on observatory.reading_checkpoints(source_id);
create index readings_source_version on observatory.readings(source_id,fingerprint);
