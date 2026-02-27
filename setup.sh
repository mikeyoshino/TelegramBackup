#!/bin/bash

echo "Starting Telegram Downloader setup..."

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Installing python3..."
    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip
fi

# Create a virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Setup complete!"
echo "To run the script, use: ./run.sh"
