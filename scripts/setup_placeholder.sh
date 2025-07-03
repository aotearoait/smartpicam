#!/bin/bash

# Setup script for placeholder image
# Run this script to set up the placeholder image for failed cameras

echo "🖼️  Setting up Camera Placeholder Image"
echo "======================================="

# Create assets directory
mkdir -p assets

echo "📁 Created assets directory"

# Instructions for user
echo ""
echo "📋 To set up your placeholder image:"
echo "  1. Save your 'No Signal' image as: assets/camera_offline.png"
echo "  2. Recommended size: 854x480 pixels (matches camera layout)"
echo "  3. Supported formats: PNG, JPG"
echo ""

# Check if image already exists
if [ -f "assets/camera_offline.png" ]; then
    echo "✅ Placeholder image found: assets/camera_offline.png"
    
    # Get image dimensions if possible
    if command -v identify &> /dev/null; then
        echo "📐 Image dimensions: $(identify assets/camera_offline.png | awk '{print $3}')"
    fi
else
    echo "⚠️  Placeholder image not found"
    echo "   Copy your image to: assets/camera_offline.png"
fi

echo ""
echo "🎯 Placeholder Features:"
echo "  • Shows for failed/timed out cameras"
echo "  • Maintains grid layout"
echo "  • Fallback to text if image missing"
echo "  • Configurable colors and text"
echo ""

# Test the optimized configuration
if [ -f "config/smartpicam_optimized.json" ]; then
    echo "✅ Optimized configuration found"
    echo "📝 To test with placeholders:"
    echo "   python3 smartpicam_optimized.py config/smartpicam_optimized.json"
else
    echo "⚠️  Optimized configuration not found"
    echo "   Make sure to pull latest changes: git pull origin performance-optimizations"
fi

echo ""
echo "🔧 Configuration Options:"
echo "  show_placeholders: true/false"
echo "  placeholder_image: path to your image"
echo "  placeholder_text_color: color for fallback text"
echo "  placeholder_bg_color: background color"
