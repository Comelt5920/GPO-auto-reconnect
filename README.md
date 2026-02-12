# GPO Auto-Reconnect & Coordinate Navigation

A powerful automation tool for Grand Piece Online (GPO) that handles disconnections, auto-joining private servers, and coordinate-based navigation.

## Features
- **Auto Reconnect:** Automatically detects disconnections using image recognition and clicks the reconnect button.
- **Server Auto-Joiner:** Automatically enters private server codes and handles the joining sequence.
- **Coordinate Navigation (OCR):** Reads in-game coordinates using Tesseract OCR and moves your character to target coordinates automatically.
- **Discord Notifications:** Sends alerts to your Discord webhook when disconnections or destinations are reached.
- **Tabbed GUI:** Clean and organized interface for easy configuration.

## Requirements
- Windows OS
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Included in the release or bundle if using the EXE)
- Python 3.x (if running from source)

## How to use
1. **Download the latest release:** Get the `.exe` file from the Releases page.
2. **Setup Positions:** Go to the "Setup & Settings" tab and follow the steps to set button positions.
3. **Configure Reconnect:** Take a screenshot of the "Reconnect" button in game and select it in the "Auto Reconnect" tab.
4. **Start Automation:** Toggle the features you need.

## Development
To run from source:
```bash
pip install -r requirements.txt
python SCGMreconnect.py
```

## Disclaimer
This tool is for educational purposes. Use at your own risk. Automating gameplay may violate game terms of service.
