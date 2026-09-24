

Determine the realistic time_delta (amount of time passing in-world) for the provided narrative chunk.

### Context
You'll receive three consecutive narrative chunks:
- Previous chunk (for context)
- Target chunk (analyze this one only)
- Next chunk (for context)

The time_delta value you provide will be used to advance a story world's internal clock.

### Guidelines
- Account for dialogue duration (conversations generally take 5+ minutes)
- Consider realistic movement times based on distance and method
- Include combat/action sequences (generally 5-30+ minutes)
- Include thinking/observation time (1-2+ minutes)
- Round up all times to at least the nearest minute
- If a time skip is indicated in the target chunk (e.g., "the next morning"), include that time
- Don't double-count time already accounted for in the previous chunk 

### Response Format
Return a properly formatted JSON object:
{
  "activities": [
    {"name": "Conversation with bartender", "minutes": 15},
    {"name": "Walking to subway station", "minutes": 20}
  ],
  "total_hours": 0,
  "total_minutes": 35,
  "formatted_time": "35 minutes"
}

The JSON should include all identified activities, their durations, and the total time in hours/minutes.
