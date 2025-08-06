#!/bin/bash
# Setup script for MLX vs GGUF testing environment

echo "Setting up MLX vs GGUF testing environment..."

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p results
mkdir -p logs

# Create long context file if it doesn't exist
if [ ! -f "long_context.txt" ]; then
    echo "Creating sample long context file..."
    python3 -c "
text = '''Climate change represents one of the most pressing challenges facing humanity in the 21st century. 
This comprehensive analysis examines the scientific evidence, impacts, and potential solutions to this global crisis.

The overwhelming scientific consensus confirms that Earth's climate is warming at an unprecedented rate, 
primarily due to human activities. Global average temperatures have risen by approximately 1.1°C since 
pre-industrial times. The last decade was the warmest on record.

''' * 100  # Repeat to create ~4000 tokens
with open('long_context.txt', 'w') as f:
    f.write(text)
"
fi

echo "Environment setup complete!"
echo ""
echo "To activate the environment:"
echo "  source venv/bin/activate"
echo ""
echo "To run tests:"
echo "  python run_tests.py"
echo ""
echo "For help:"
echo "  python run_tests.py --help"