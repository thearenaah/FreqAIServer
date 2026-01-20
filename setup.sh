#!/bin/bash
# Setup script for FreqAI server

echo "Setting up FreqAI Server..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file - please configure PostgreSQL connection"
fi

# Create models directory
mkdir -p models

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure .env with your PostgreSQL credentials"
echo "2. Create database: createdb freqai_db"
echo "3. Run: python main.py"
