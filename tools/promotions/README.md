# Promotions System

## Quick Setup

1. **Copy these files** to your `tools/promotions/` directory
2. **Add to automated_price_system.py**:
   ```python
   def apply_promotions():
       import subprocess
       import os
       promo_script = os.path.join("tools", "promotions", "apply_promos.py")
       result = subprocess.run(['python', promo_script], cwd=os.getcwd())
       if result.returncode == 0:
           print("✅ Promotions applied successfully")
       else:
           print("⚠️ Warning: Promotion application failed")
   
   # Add this line to your main function:
   apply_promotions()
   ```

## Testing

1. **Test the system**:
   ```bash
   cd tools/promotions
   python apply_promos.py
   ```

2. **Use test data**: Copy `promotions_test.json` to `promotions.json` for testing

## Adding Promos

Edit `promotions.json`:

**Sitewide Example**:
```json
{
  "ci": [
    {
      "code": "HOLIDAY25",
      "discount": 25,
      "scope": "sitewide",
      "end_date": "2025-01-15",
      "active": true
    }
  ]
}
```

**Brand Example**:
```json
{
  "thompson": [
    {
      "code": "MFPADRON30",
      "discount": 30,
      "scope": "brand",
      "brands": ["My Father", "Padron"],
      "end_date": "2025-01-20",
      "active": true
    }
  ]
}
```

## File Structure

- `promotions.json` - Your active promo data
- `promo_manager.py` - Core logic
- `apply_promos.py` - CSV processor
- `promotions_test.json` - Test data
