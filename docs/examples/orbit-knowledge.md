# Orbit Sync demo knowledge

This is a fictional example for testing Agent Utka.

## Sync worker retry policy

The Orbit sync worker waits 5 seconds before retrying a temporary failure.

Permanent errors are reported immediately and are never retried.

## Glossary

`syncJobId` identifies a single run of the Orbit sync worker.

```utka-cue-asr
{
  "terms": ["syncJobId"],
  "hotwords": ["syncJobId"],
  "aliases": [
    {"term": "syncJobId", "heard": ["sync job ID"]}
  ]
}
```
