
Return ONLY a valid JSON object adhering strictly to the following schema:
```json
{
  "chunk_id": "{{CHUNK_ID}}",
  "reasoning": "1-2 sentences explaining your decision process for selecting this location",
  "primary_location": {
    "status": "known OR new",
    
    /* For known locations (status="known"): */
    "id": 123, /* matching ID from the KNOWN LOCATIONS LIST */
    "confidence": 0.9,
    
    /* For new locations (status="new"): */
    "name": "Location name",
    "type": "fixed_location|vehicle|other",
    "zone": 1, /* matching ID from the KNOWN LOCATIONS LIST */
    "confidence": 0.9
  },
  "mentioned_locations": [
    /* Same structure as primary_location */
  ]
}
```
