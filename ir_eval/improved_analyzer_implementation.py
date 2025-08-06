
def _analyze_query(self, query_text: str) -> Dict[str, Any]:
    """
    Analyze the query to determine type and characteristics.
    Improved version with better pattern matching based on evaluation results.
    
    Args:
        query_text: The query string to analyze
        
    Returns:
        Dictionary with query analysis results
    """
    # Simple rule-based analysis
    query_info = {
        "text": query_text,
        "type": "general"  # Default
    }
    
    # Convert to lowercase for pattern matching
    query_lower = query_text.lower()
    
    # Check for character-focused query (highest priority to match confusion matrix)
    character_patterns = [
        r"\b(alex|emilia|pete|alina|dr\. nyati|stacey|amanda|liz|michael|david|james|sarah)\b",  # Extended character names
        r"\bwho (is|was|are|were)\b",
        r"\bcharacter['s]?\b",
        r"\bperson['s]?\b",
        r"\b(his|her|their) (personality|background|history|appearance)\b",
        r"\bdescribe [a-z]+ (personality|appearance)\b",
        r"\bwhat (is|was) [a-z]+ like\b",
        r"\babout [a-z]+'s (personality|background|history|appearance)\b",
        r"\b(gender|age|name|alias|occupation|job)\b"
    ]
    
    for pattern in character_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "character"
            return query_info  # Early return since character has highest priority
    
    # Check for relationship-focused query
    relationship_patterns = [
        r"\brelationship\b",
        r"\bfeel[s]? about\b",
        r"\bthink[s]? about\b",
        r"\bfeel[s]? towards\b",
        r"\bthink[s]? of\b",
        r"\b(how|what) does [a-z]+ (feel|think) about\b",
        r"\b(like|hate|love|trust|distrust|respect)\b [a-z]+\b",
        r"\b(friend|enemy|ally|lover|partner|colleague|mentor|rival)\b",
        r"\b(connection|interaction|dynamic) (with|between)\b",
        r"\b(dating|married|involved with|working with)\b"
    ]
    
    for pattern in relationship_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "relationship"
            return query_info  # Early return for next priority
    
    # Check for event-focused query
    event_patterns = [
        r"\bwhat happened\b",
        r"\bevent[s]?\b",
        r"\boccurred\b",
        r"\btook place\b",
        r"\bwhen (did|was|were)\b",
        r"\b(timeline|chronology|sequence) of\b",
        r"\b(before|after|during) [a-z]+\b",
        r"\bincident[s]?\b",
        r"\baction[s]?\b",
        r"\b(mission|operation|meeting|fight|battle|conflict|confrontation)\b",
        r"\b(how|why|when) did [a-z]+ (happen|start|end|occur)\b",
        r"\bvisit(ed)? [a-z]+\b"
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "event"
            return query_info
    
    # Check for location-focused query
    location_patterns = [
        r"\bwhere\b",
        r"\blocation['s]?\b",
        r"\bplace['s]?\b",
        r"\b(city|district|area|region|zone|neighborhood)['s]?\b",
        r"\b(building|facility|complex|headquarters|center|base)['s]?\b",
        r"\bwhat is [a-z]+ (like|layout|description)\b",
        r"\b(bar|club|restaurant|office|laboratory|lab|bridge)['s]?\b",
        r"\bdescribe [a-z]+ (layout|appearance|design)\b",
        r"\b(what|where) is\b [a-z]+ (located|situated)"
    ]
    
    for pattern in location_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "location"
            return query_info
    
    # Check for theme-focused query
    theme_patterns = [
        r"\btheme[s]?\b",
        r"\bmotif[s]?\b",
        r"\bsymbolism\b",
        r"\bmeaning\b",
        r"\bconcept[s]?\b",
        r"\bsignificance\b",
        r"\bimportance\b",
        r"\bpurpose\b",
        r"\bgoal[s]?\b",
        r"\bmission\b",
        r"\bphilosophy\b",
        r"\bideology\b",
        r"\b(what is the|what's the) (point|purpose|goal|meaning)\b",
        r"\b(why does|why is|why was) [a-z]+ (important|significant|created|developed)"
    ]
    
    for pattern in theme_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "theme"
            return query_info
    
    # If no patterns matched, it remains "general"
    return query_info
