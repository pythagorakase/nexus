
# Standard Query-Passage Pairs
{
  "query": "Who is Emilia?",
  "positive": "Emilia is a special-case character in the interactive narrative, fully autonomous and not user-controllable.",
  "negative": "The setting of Night City is inspired by cyberpunk influences."
}

# Narrative Memory Retrieval Pairs
{
  "query": "Last time Alex spoke to Nyati, what did she say?",
  "positive": "Dr. Nyati warned Alex about the risks of deep-dive virtualizations, mentioning a past incident.",
  "negative": "Dr. Nyati is a scientist working on cognitive AI enhancements."
}

# Thematic & Conceptual Retrieval Pairs
{
  "query": "Cybernetic augmentation philosophy",
  "positive": "Transhumanism and cybernetics redefine the boundaries of identity and human potential.",
  "negative": "Virtual hacking techniques involve manipulating data structures inside a cyberspace grid."
}

# Structured Information Retrieval Pairs
{
  "query": "Where is the Combat Zone?",
  "positive": "The Combat Zone is a lawless region on the outskirts of Night City, ruled by gangs and mercenaries.",
  "negative": "Neon Bay is an elite corporate sector known for its high-security zones."
}

# Contrastive Pairs

training_data = [
    # Positive pair - these should be close in the embedding space
    {
        "text1": "The netrunner interfaced with the system, fingers dancing across the neural link.",
        "text2": "You connected to the network, your hands moving rapidly over the neural interface.",
        "label": 1.0  # 1.0 means similar
    },
    
    # Negative pair - these should be distant in the embedding space
    {
        "text1": "The netrunner interfaced with the system, fingers dancing across the neural link.",
        "text2": "Emilia ordered another drink at the bar, watching the crowd with suspicion.",
        "label": 0.0  # 0.0 means dissimilar
    }
]

# Query-Based Triplets
training_data = [
    {
        "query": "How did Alex and Emilia first meet?",
        "positive_passage": "The job at Dynacorp was supposed to be simple. You were there to extract data, she was there to stop you. Your eyes met across the server room, her pistol aimed at your chest. 'Stealing corporate secrets is still stealing,' she said, though something in her voice suggested she wasn't entirely convinced of Dynacorp's virtue.",
        "negative_passage": "Dr. Nyati examined the implant with a frown. 'This neural dampener is experimental tech. Military grade. Not something you'd find on the open market.' You watched as she placed it in a sealed container. 'Someone wanted to make sure you couldn't access certain memories.'"
    },
    
    {
        "query": "What happened at the Bridge?",
        "positive_passage": "The Bridge wasn't physical space—not exactly. As your consciousness slipped into the strange dimensional fold, colors that had no right to exist swirled around you. Time didn't flow here, it pooled. 'Don't lose yourself,' Alina had warned. 'The Bridge remembers everyone who crosses it.'",
        "negative_passage": "The Combat Zone erupted in gunfire as rival gangs fought for territory. You pulled Emilia behind a concrete barrier as bullets pinged off the metal around you. 'This wasn't in the plan,' she hissed, checking her weapon."
    }
]

## Example 1: Character Relationship Dynamics
{
    "query": "What is the nature of Alex and Emilia's relationship?",
    "positive_passage": "You caught Emilia watching you when she thought you weren't looking. There was something in her gaze—concern, maybe, or calculation. With her, it was always hard to tell which. 'I don't trust Lansky,' she said finally. 'But I trust you.' Coming from Emilia, that admission cost something. You both knew it.",
    "negative_passage": "The Wastes stretched before you, a desolate expanse of pollution and abandoned structures. Radiation warnings flashed on your HUD as you navigated the terrain. This had been fertile farmland once, before the corporate wars."
}

## Example 2: Location Description Recognition
{
    "query": "Describe The Underbelly district.",
    "positive_passage": "The lower levels of Night City never saw true daylight. Here in The Underbelly, everything was illuminated by the sickly glow of neon and the occasional spark of illicit tech. The smell of synthetic food mingled with damp concrete and desperation. This was where dreams came to die—or mutate into something unrecognizable.",
    "negative_passage": "Corporate Spires reached toward the clouds, glass and steel monuments to power and wealth. From this height, the rest of Night City looked like a circuit board, pulsing with tiny lights. The air was cleaner up here, filtered and perfumed for the comfort of those who could afford altitude."
}
## Example 3: Technological Concepts
{
    "query": "How does neural virtualization work?",
    "positive_passage": "The virtualization rig hummed as you slid the neural spike into your interface port. Reality dissolved around you, replaced by the constructed digital landscape. Here, thoughts became architecture. Memory became terrain. The boundaries between your consciousness and the system blurred until you couldn't tell where you ended and the code began.",
    "negative_passage": "The black market clinic was hidden behind a laundromat. Dr. Nyati gestured to the surgical chair. 'This implant will enhance your visual spectrum,' she explained, holding up the tiny cybernetic component. 'Infrared, ultraviolet, and thermal imaging. Military grade, so don't ask where I got it.'"
}

# Multiple Negatives (Enhanced Approach)
training_data = [
    {
        "anchor": "Alex found the hidden passage behind the holographic advertisement.",
        "positive": "You discovered a secret doorway concealed behind the flickering neon display.",
        "negatives": [
            "Emilia hacked into the corporate database, bypassing three layers of ICE.",
            "The rain fell heavily on the neon-lit streets of Night City.",
            "Dr. Nyati explained how the neural implant was affecting your memories."
        ]
    }
]
