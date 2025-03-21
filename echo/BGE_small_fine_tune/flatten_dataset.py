import json
import os
import re
import unicodedata
from itertools import product
from collections import defaultdict, Counter

def flatten_dataset(input_file, output_file):
    """
    Flattens a hierarchical JSON dataset into query-positive-negative triplets
    for BGE-Small fine-tuning.
    """
    print(f"Processing {input_file}...")
    
    # Load dataset
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Track statistics for debugging
    stats = {
        "triplets": [],
        "processed_queries": set(),
        "skipped_entities": [],
        "pos_counts": defaultdict(int),
        "neg_counts": defaultdict(int),
        "positives_total": 0,
        "negatives_total": 0,
        "queries_total": 0,
        "all_queries": [],
        "all_positives": [],
        "all_negatives": [],
        "category_data": defaultdict(lambda: {
            "queries": [],
            "positives": [],
            "negatives": []
        }),
        "entity_aliases": {},
        "alias_query_variations": 0,
        "alias_templates": 0
    }
    
    # Process all major categories
    for category_name, category_data in data.items():
        print(f"Processing category: {category_name}")
        
        if not isinstance(category_data, dict):
            print(f"  Skipping non-dict category: {category_name}")
            continue
            
        # Process each entity in the category
        for entity_name, entity_data in category_data.items():
            # Extract aliases if they exist
            if isinstance(entity_data, dict) and "aliases" in entity_data:
                if isinstance(entity_data["aliases"], list) and all(isinstance(item, str) for item in entity_data["aliases"]):
                    stats["entity_aliases"][f"{category_name}/{entity_name}"] = entity_data["aliases"]
                    print(f"  Found aliases for {category_name}/{entity_name}: {len(entity_data['aliases'])} aliases")
            
            # Process the entity
            process_entity(
                category_name, 
                entity_name, 
                entity_data, 
                stats, 
                path=f"{category_name}/{entity_name}"
            )
    
    # Generate triplets
    triplets = []
    
    # 1. First generate local triplets (query paired with its own positives/negatives)
    local_triplet_count = len(stats["triplets"])
    triplets.extend(stats["triplets"])
    print(f"\nGenerated {local_triplet_count} local triplets")
    
    # 2. Now generate in-category triplets
    print("\nGenerating in-category triplets...")
    
    category_triplet_count = 0
    in_category_combinations = set()
    
    # Add existing combinations to the set
    for triplet in stats["triplets"]:
        in_category_combinations.add((triplet["query"], triplet["positive"], triplet["negative"]))
    
    # Generate in-category triplets for each category
    for category, cat_data in stats["category_data"].items():
        cat_queries = cat_data["queries"]
        cat_positives = cat_data["positives"]
        cat_negatives = cat_data["negatives"]
        
        if not cat_queries or not cat_positives or not cat_negatives:
            continue
            
        print(f"  Category {category}: {len(cat_queries)} queries, {len(cat_positives)} positives, {len(cat_negatives)} negatives")
        
        # Set a reasonable limit per category to avoid explosion
        max_per_category = 10000
        combinations_per_query = max(1, min(100, max_per_category // len(cat_queries)))
        
        import random
        random.seed(42)  # For reproducibility
        
        # For each query, generate some combinations
        category_combinations = 0
        for query_data in cat_queries:
            query_path, query = query_data
            
            # Sample a subset of positives and negatives for this query
            sampled_positives = random.sample(cat_positives, min(len(cat_positives), 10))
            sampled_negatives = random.sample(cat_negatives, min(len(cat_negatives), 10))
            
            # Generate combinations
            for pos, neg in product(sampled_positives, sampled_negatives):
                # Skip if this combination already exists
                if (query, pos, neg) in in_category_combinations:
                    continue
                    
                triplets.append({
                    "query_id": f"cat_{category}_{hash(query) % 10000}",
                    "query": normalize_unicode(query),
                    "positive": normalize_unicode(pos),
                    "negative": normalize_unicode(neg)
                })
                
                category_triplet_count += 1
                category_combinations += 1
                in_category_combinations.add((query, pos, neg))
                
                # Limit combinations per query
                if category_combinations >= combinations_per_query * len(cat_queries):
                    break
            
            # Break if we've reached the limit for this category
            if category_combinations >= combinations_per_query * len(cat_queries):
                break
    
    # 3. Generate alias-based triplets using improved strategy
    alias_triplets = generate_alias_triplets(data, stats)
    triplets.extend(alias_triplets)
    alias_triplet_count = len(alias_triplets)
    
    # Clean all strings in triplets to avoid Unicode issues
    for triplet in triplets:
        for key in ["query", "positive", "negative"]:
            if key in triplet:
                triplet[key] = clean_text_for_output(triplet[key])
    
    # Write flattened dataset with proper encoding
    # Use a custom approach that avoids Unicode escapes but still produces valid JSON
    clean_json = json.dumps(triplets, indent=2, ensure_ascii=False)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(clean_json)
    
    # Print detailed statistics
    print("\n=== STATISTICS ===")
    print(f"Generated {len(triplets)} total training examples")
    print(f"  - {local_triplet_count} local triplets (query with its own positives/negatives)")
    print(f"  - {category_triplet_count} in-category triplets")
    print(f"  - {alias_triplet_count} alias-based triplets")
    print(f"    - Query variations: {stats['alias_query_variations']}")
    print(f"    - Template variations: {stats['alias_templates']}")
    print(f"From {len(stats['processed_queries'])} unique queries")
    print(f"Total queries found: {stats['queries_total']}")
    print(f"Total positives found: {stats['positives_total']}")
    print(f"Total negatives found: {stats['negatives_total']}")
    
    print("\nCategories:")
    for category, cat_data in sorted(stats["category_data"].items()):
        if cat_data["queries"]:
            print(f"  {category}: {len(cat_data['queries'])} queries, {len(cat_data['positives'])} positives, {len(cat_data['negatives'])} negatives")
    
    print("\nAliases:")
    total_aliases = sum(len(aliases) for aliases in stats["entity_aliases"].values())
    print(f"  Found {len(stats['entity_aliases'])} entities with aliases ({total_aliases} total aliases)")
    
    print("\nTop query entities:")
    query_path_counter = Counter(q_path for q_path, _ in stats["all_queries"])
    for entity, count in query_path_counter.most_common(5):
        print(f"  {entity}: {count} queries")
    
    print("\nTop entities by positive count:")
    for entity, count in sorted(stats["pos_counts"].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {entity}: {count} positives")
        
    print("\nTop entities by negative count:")
    for entity, count in sorted(stats["neg_counts"].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {entity}: {count} negatives")
    
    return {
        "total_triplets": len(triplets),
        "local_triplets": local_triplet_count,
        "category_triplets": category_triplet_count,
        "alias_triplets": alias_triplet_count,
        "alias_query_variations": stats["alias_query_variations"],
        "alias_templates": stats["alias_templates"],
        "unique_queries": len(stats['processed_queries']),
        "total_positives": stats['positives_total'],
        "total_negatives": stats['negatives_total']
    }

def normalize_unicode(text):
    """
    Normalize Unicode characters to avoid ambiguity.
    This function:
    1. Normalizes to NFKC form (compatibility decomposition followed by canonical composition)
    2. Removes control characters and zero-width spaces
    3. Replaces problematic characters with standard ASCII equivalents
    """
    if not isinstance(text, str):
        return text
        
    # Normalize to NFKC form
    normalized = unicodedata.normalize('NFKC', text)
    
    # Remove control characters and zero-width spaces
    normalized = re.sub(r'[\u0000-\u001F\u007F-\u009F\u200B-\u200D\uFEFF]', '', normalized)
    
    # Replace common problematic characters
    replacements = {
        '"': '"',  # Smart quotes
        '"': '"',
        ''': "'",
        ''': "'",
        '–': '-',  # En dash
        '—': '-',  # Em dash
        '…': '...',  # Ellipsis
        '\u2028': ' ',  # Line separator
        '\u2029': ' '   # Paragraph separator
    }
    
    for orig, repl in replacements.items():
        normalized = normalized.replace(orig, repl)
    
    return normalized

def clean_text_for_output(text):
    """
    Perform final cleaning of text for output to ensure no ambiguous Unicode characters remain.
    This function:
    1. First normalizes the Unicode
    2. Then converts any remaining non-ASCII characters to their closest ASCII equivalents
    3. Falls back to removing characters that can't be safely represented
    """
    if not isinstance(text, str):
        return text
    
    # First normalize
    text = normalize_unicode(text)
    
    # Additional replacements for common Unicode characters
    more_replacements = {
        '\u2013': '-',  # en dash
        '\u2014': '-',  # em dash
        '\u2018': "'",  # left single quote
        '\u2019': "'",  # right single quote
        '\u201C': '"',  # left double quote
        '\u201D': '"',  # right double quote
        '\u2022': '*',  # bullet
        '\u2026': '...', # ellipsis
        '\u00A0': ' ',  # non-breaking space
        '\u00AD': '-',  # soft hyphen
        '\u00AE': '(R)', # registered trademark
        '\u00A9': '(C)', # copyright
        '\u00B0': ' degrees', # degree symbol
        '\u00B1': '+/-', # plus-minus
        '\u00B7': '*',  # middle dot
    }
    
    for orig, repl in more_replacements.items():
        text = text.replace(orig, repl)
    
    # Remove any remaining non-ASCII characters that couldn't be converted
    # text = re.sub(r'[^\x00-\x7F]', '', text)
    
    return text

def safe_id(text):
    """Create a safe ID string from text."""
    return re.sub(r'[^a-zA-Z0-9]', '_', text[:10])

def generate_alias_triplets(dataset, stats):
    """Generate alias-based triplets in a more natural way."""
    alias_triplets = []
    alias_map = {}
    
    # 1. First identify all character aliases
    for entity_name, entity_data in dataset.get("characters", {}).items():
        if "aliases" in entity_data and isinstance(entity_data["aliases"], list):
            aliases = entity_data["aliases"]
            if aliases:
                alias_map[entity_name] = aliases
                print(f"Found aliases for {entity_name}: {aliases}")
    
    # 2. For each character with aliases
    for character_name, aliases in alias_map.items():
        character_data = dataset["characters"][character_name]
        
        # Find existing character queries that have positives and negatives
        for subcat, subcat_data in character_data.items():
            if isinstance(subcat_data, dict) and "query" in subcat_data:
                original_query = subcat_data["query"]
                
                positives = [v for k, v in subcat_data.items() if k.startswith("positive") and isinstance(v, str)]
                negatives = [v for k, v in subcat_data.items() if k.startswith("negative") and isinstance(v, str)]
                
                if not positives or not negatives:
                    continue
                
                # 3. Create contextual alias variations only if character name appears in query
                if character_name in original_query:
                    for alias in aliases:
                        # Only replace the character name if it appears in the query
                        if character_name in original_query:
                            alias_query = original_query.replace(character_name, alias)
                            
                            # Only add if the query actually changed
                            if alias_query != original_query:
                                # Create triplets using all combinations
                                for pos, neg in product(positives, negatives):
                                    query_id = f"alias_{character_name}_{alias}_{safe_id(original_query)}"
                                    alias_triplets.append({
                                        "query_id": query_id,
                                        "query": normalize_unicode(alias_query),
                                        "positive": normalize_unicode(pos),
                                        "negative": normalize_unicode(neg)
                                    })
                                    stats["alias_query_variations"] += 1
                
                # 4. For character-specific patterns, create natural template variations
                # Define common query patterns in your dataset
                templates = [
                    (f"What is {character_name}'s background?", f"What is {{}}'s background?"),
                    (f"How did {character_name} react", f"How did {{}} react"),
                    (f"What does {character_name} look like?", f"What does {{}} look like?"),
                    (f"Who is {character_name}?", f"Who is {{}}?")
                ]
                
                for template_pattern, template_format in templates:
                    if original_query == template_pattern:
                        for alias in aliases:
                            alias_query = template_format.format(alias)
                            
                            # Create triplets using all combinations
                            for pos, neg in product(positives, negatives):
                                query_id = f"template_{character_name}_{alias}_{safe_id(original_query)}"
                                alias_triplets.append({
                                    "query_id": query_id,
                                    "query": normalize_unicode(alias_query),
                                    "positive": normalize_unicode(pos),
                                    "negative": normalize_unicode(neg)
                                })
                                stats["alias_templates"] += 1
    
    print(f"Generated {len(alias_triplets)} alias-based triplets")
    print(f"- Query variations: {stats['alias_query_variations']}")
    print(f"- Template variations: {stats['alias_templates']}")
    
    return alias_triplets
    
def process_entity(category_name, entity_name, entity_data, stats, path=""):
    """Process a single entity, handling any level of nesting."""
    # Skip if this is an array of strings (but not aliases - we handle those separately)
    if isinstance(entity_data, list) and all(isinstance(item, str) for item in entity_data):
        if not path.endswith("/aliases"):  # Don't log aliases as skipped
            stats["skipped_entities"].append(f"{path} (string array)")
        return
        
    # If this is not a dictionary, skip
    if not isinstance(entity_data, dict):
        stats["skipped_entities"].append(f"{path} (not a dict)")
        return
        
    # Check if this entity has a direct query
    if "query" in entity_data:
        process_query_object(entity_data, stats, path, category_name)
    
    # Even if we found a query, we should still process all sub-entities
    for sub_name, sub_data in entity_data.items():
        # Skip aliases - we handle them separately
        if sub_name == "aliases":
            continue
            
        # Skip string values and already processed query
        if isinstance(sub_data, str) or sub_name == "query":
            continue
            
        # Process the sub-entity if it's a dict or list
        if isinstance(sub_data, (dict, list)):
            process_entity(
                category_name, 
                f"{entity_name}/{sub_name}", 
                sub_data, 
                stats, 
                path=f"{path}/{sub_name}"
            )

def process_query_object(query_obj, stats, path, category_name):
    """Process an object that contains a query."""
    # Extract query
    query = query_obj.get("query", "")
    if not query:
        stats["skipped_entities"].append(f"{path} (empty query)")
        return
        
    # Track that we processed this query
    stats["processed_queries"].add(query)
    stats["queries_total"] += 1
    stats["all_queries"].append((path, query))
    
    # Add to category data
    stats["category_data"][category_name]["queries"].append((path, query))
    
    # Collect positives and negatives
    positives = []
    negatives = []
    
    # Look for positive/negative keys at any level of nesting
    collect_examples(query_obj, positives, negatives, stats, path)
    
    # Print diagnostics for each query
    print(f"  Query at {path}: {len(positives)} positives, {len(negatives)} negatives")
    
    # Update total counts
    stats["positives_total"] += len(positives)
    stats["negatives_total"] += len(negatives)
    
    # Add to global and category collections
    stats["all_positives"].extend(positives)
    stats["all_negatives"].extend(negatives)
    stats["category_data"][category_name]["positives"].extend(positives)
    stats["category_data"][category_name]["negatives"].extend(negatives)
    
    # Generate combinations only if we have both positives and negatives
    if not positives:
        print(f"    WARNING: No positives for query at {path}")
        return
        
    if not negatives:
        print(f"    WARNING: No negatives for query at {path}")
        return
    
    # Generate all combinations
    query_id = f"{path}_{query[:20].replace(' ', '_')}"
    for pos, neg in product(positives, negatives):
        stats["triplets"].append({
            "query_id": query_id,
            "query": normalize_unicode(query),
            "positive": normalize_unicode(pos),
            "negative": normalize_unicode(neg)
        })

def collect_examples(obj, positives, negatives, stats, path):
    """Recursively collect positive and negative examples from any level of nesting."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                if key.startswith("positive"):
                    positives.append(value)
                    stats["pos_counts"][path] += 1
                elif key.startswith("negative"):
                    negatives.append(value)
                    stats["neg_counts"][path] += 1
            elif isinstance(value, (dict, list)):
                # Recursively search nested structures
                collect_examples(value, positives, negatives, stats, path)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                collect_examples(item, positives, negatives, stats, path)

if __name__ == "__main__":
    input_file = "BGE_small_training_dataset_final_draft.json"
    output_file = "BGE_small_training_triplets.json"
    
    stats = flatten_dataset(input_file, output_file)
    print(f"\nFinal Statistics: {stats}")