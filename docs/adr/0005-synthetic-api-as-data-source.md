# The data source is a synthetic API we run ourselves

The pipeline extracts from a small FastAPI service we run in Docker, not from a live third-party API. It exposes `/orders?created_after=…&created_before=…&page=…` over a seeded, deterministic generator, and can be told to return 500s, 429s, or hang on demand.

A live public API was rejected for three reasons. Reproducibility: every re-run of the same backfill window would return different data, which destroys the feedback loop the method depends on — re-run the lesson, get a different answer, and you can no longer tell whether the lesson or the code is wrong. Late-arriving facts: the condition that separates an incremental `insert` from an incremental `merge` cannot be demonstrated against an API that is consistent on read, so the generator produces them deliberately instead. Controlled failure: retries, timeouts, and sensors cannot be practised against a third party that misbehaves on cue.

The service is a **frozen fixture** during the course — lessons are written against its schema, and modifying it invalidates them. The final module is where it gets deliberately broken, so the pipeline's failure behaviour can be observed end to end.
