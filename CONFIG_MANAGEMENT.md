# Configuration Management Guide

## 🔒 **Protecting Your Configuration**

Your camera configuration files containing URLs and passwords are now protected from being overwritten by git updates.

## 📁 **File Structure**

```
smartpicam/
├── config/
│   ├── smartpicam.json                    # YOUR config (protected by .gitignore)
│   ├── smartpicam_optimized.json          # YOUR optimized config (protected)
│   └── smartpicam_optimized.json.example  # Template/example file
```

## 🚀 **Setting Up Your Configuration**

### **First Time Setup:**
```bash
cd ~/smartpicam/config

# Copy the example to create your own config
cp smartpicam_optimized.json.example smartpicam_optimized.json

# Edit with your camera details
nano smartpicam_optimized.json
```

### **Updating Configuration:**
When new features are added, you can:

1. **See what's new** in the example:
   ```bash
   diff smartpicam_optimized.json smartpicam_optimized.json.example
   ```

2. **Manually add new options** to your config file

3. **Or start fresh** (backup first):
   ```bash
   cp smartpicam_optimized.json smartpicam_optimized.json.backup
   cp smartpicam_optimized.json.example smartpicam_optimized.json
   # Then re-add your camera URLs and passwords
   ```

## 🔧 **New Configuration Options**

The optimized configuration now includes:

### **Performance Options:**
```json
{
  "display": {
    "hardware_accel": true,           // Enable Pi 5 GPU acceleration
    "low_latency": true,              // Optimize for low latency
    "buffer_size": "32k",             // Small buffers for less memory
    "thread_count": 1,                // Threads per camera stream
    "skip_failed_cameras": false      // Show all cameras (with placeholders)
  }
}
```

### **Placeholder Options:**
```json
{
  "display": {
    "show_placeholders": true,              // Show failed camera placeholders
    "placeholder_image": "feed-unavailable.png",  // Your custom image
    "placeholder_text_color": "white",      // Text color (if no image)
    "placeholder_bg_color": "darkgray"      // Background color
  }
}
```

### **Auto-Recovery Options:**
```json
{
  "display": {
    "enable_camera_retry": true,      // Enable automatic camera recovery
    "camera_retry_interval": 30       // Test failed cameras every N seconds
  }
}
```

## 📋 **Safe Update Process**

When you pull updates:

```bash
cd ~/smartpicam
git pull origin performance-optimizations
```

Your configuration files will **NOT** be overwritten! ✅

## 🔍 **Checking for New Options**

After updates, check if new options were added:

```bash
# See what's new in the example
cat config/smartpicam_optimized.json.example

# Compare with your config
diff config/smartpicam_optimized.json config/smartpicam_optimized.json.example
```

## 🛡️ **Backup Strategy**

Always backup your working config before major changes:

```bash
# Create timestamped backup
cp config/smartpicam_optimized.json config/smartpicam_optimized.json.$(date +%Y%m%d_%H%M%S)
```

## 📝 **Configuration Best Practices**

1. **Keep passwords secure** - your config files are now ignored by git
2. **Test changes incrementally** - enable one new feature at a time
3. **Backup working configs** - before making major changes
4. **Use example file** as reference for new features
5. **Document your changes** - add comments explaining custom settings

## 🚨 **Important Notes**

- Your `config/smartpicam.json` and `config/smartpicam_optimized.json` files are now **protected**
- Git will never overwrite them again
- You control when and how to update your configuration
- Example files show you what new features are available

This ensures your camera configurations, passwords, and custom settings remain safe during updates! 🔒
