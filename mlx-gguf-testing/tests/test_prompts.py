"""Test prompts for MLX vs GGUF testing."""

# Standard test prompts
TEST_PROMPTS = {
    "simple": "Explain quantum entanglement in simple terms, using about 200 words.",
    
    "math": """Solve step by step: If a train travels 120km in 1.5 hours, what is its average speed? 
Then calculate how long it would take to travel 300km at that speed.""",
    
    "creative": "Write a haiku about artificial intelligence, then explain your creative choices.",
    
    "code": """Write a Python function to calculate fibonacci numbers efficiently using memoization. 
Include proper docstring and type hints.""",
    
    "reasoning": """What are the pros and cons of remote work? 
Consider productivity, work-life balance, and team collaboration.""",
    
    "memory_test": """List 20 different types of fruits, then categorize them by:
1. Color (red, yellow, green, etc.)
2. Origin (tropical, temperate, etc.)
3. Typical season when available""",
    
    "moe_math": """Solve this calculus problem step by step:
Find the derivative of f(x) = x³sin(x) + e^(2x)cos(x).
Then find the critical points and determine if they are maxima or minima.""",
    
    "moe_creative": """Write a short story (200 words) about a robot learning to paint. 
Include vivid sensory descriptions and explore themes of creativity and consciousness.""",
    
    "moe_code": """Implement a binary search tree in Python with the following methods:
- insert(value)
- search(value)
- delete(value)
- inorder_traversal()
Include edge case handling and time complexity analysis.""",
    
    "moe_factual": """Provide a comprehensive interdisciplinary analysis covering:
1. Biochemistry: Explain CRISPR-Cas9 mechanism, PAM sequences, and off-target effects
2. Quantum Physics: Derive the transmission coefficient for quantum tunneling through a rectangular barrier
3. Machine Learning: Compare backpropagation in CNNs vs Transformers, including gradient flow
4. Molecular Biology: Detail the role of RNA interference in gene regulation
5. Astrophysics: Explain neutron star formation and degenerate matter
6. Computer Science: Analyze P vs NP problem implications for cryptography
Connect these topics by exploring how quantum computing might revolutionize both gene editing algorithms and neural network training.""",
    
    "factual": """Explain the following scientific concepts:
1. How does CRISPR gene editing work?
2. What is quantum tunneling?
3. How do neural networks learn?
Provide clear, accurate explanations suitable for a college undergraduate."""
}

# Long context document (4000 tokens ~ 3000 words)
LONG_CONTEXT_TEMPLATE = """
Climate change represents one of the most pressing challenges facing humanity in the 21st century. 
This comprehensive analysis examines the scientific evidence, impacts, and potential solutions to 
this global crisis.

## Scientific Evidence

The overwhelming scientific consensus confirms that Earth's climate is warming at an unprecedented 
rate, primarily due to human activities. Key evidence includes:

1. **Temperature Records**: Global average temperatures have risen by approximately 1.1°C since 
pre-industrial times. The last decade was the warmest on record, with 2023 marking another year 
of extreme heat events worldwide.

2. **Greenhouse Gas Concentrations**: Atmospheric CO2 levels have increased from 280 ppm in 
pre-industrial times to over 420 ppm today - the highest in over 3 million years. Methane and 
other greenhouse gases show similar dramatic increases.

3. **Ice Loss**: Arctic sea ice is declining at a rate of 13% per decade. The Greenland and 
Antarctic ice sheets are losing mass at accelerating rates, contributing to sea level rise.

4. **Ocean Changes**: Ocean temperatures are rising, with the top 2000 meters warming by 0.33°C 
since 1969. Ocean acidification, caused by CO2 absorption, threatens marine ecosystems.

[Content continues for approximately 3000 more words covering impacts, regional variations, 
economic consequences, technological solutions, policy responses, and future projections...]

## Conclusion

Addressing climate change requires unprecedented global cooperation and immediate action across 
all sectors of society. While the challenges are immense, the combination of technological 
innovation, policy implementation, and behavioral change offers pathways to a sustainable future. 
The next decade will be critical in determining whether humanity can limit warming to manageable 
levels and adapt to the changes already set in motion.

Please provide a comprehensive summary of this document, highlighting:
1. The main scientific evidence presented
2. Key impacts discussed
3. Proposed solutions
4. The overall message and urgency conveyed
"""

def get_long_context() -> str:
    """Get the full long context document."""
    # In a real implementation, this would load from a file
    # For now, we'll repeat the template to reach ~4000 tokens
    return LONG_CONTEXT_TEMPLATE * 3