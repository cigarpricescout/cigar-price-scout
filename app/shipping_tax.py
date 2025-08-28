def zip_to_state(zip_code):
  if not zip_code:
      return 'OR'

  # Clean the ZIP code
  zip_str = str(zip_code).strip()
  if len(zip_str) < 3:
      return 'OR'

  # Check first 3 digits for more accurate mapping
  first_three = zip_str[:3]

  # Oregon specific mapping (970-979)
  if first_three.startswith('97'):
      return 'OR'

  # Washington (980-994) 
  if first_three.startswith('98') or first_three.startswith('99'):
      return 'WA'

  # California (900-969)
  if zip_str[0] == '9' and not first_three.startswith('97') and not first_three.startswith('98') and not first_three.startswith('99'):
      return 'CA'

  # Other states by first digit
  first_digit = zip_str[0]
  states = {
      '0': 'MA', '1': 'NY', '2': 'VA', '3': 'FL', '4': 'OH', 
      '5': 'MN', '6': 'IL', '7': 'TX', '8': 'CO'
  }
  return states.get(first_digit, 'OR')

def estimate_shipping_cents(base_price_cents, retailer_key, state=None):
  if retailer_key == 'famous':
      return 999
  elif retailer_key == 'ci':
      return 895
  else:
      return 999

def estimate_tax_cents(base_price_cents, state):
  if not state:
      return 0
  rates = {
      'CA': 0.08, 'NY': 0.08, 'TX': 0.06, 'FL': 0.06, 
      'OR': 0.0, 'WA': 0.065, 'NH': 0.0, 'MT': 0.0, 'DE': 0.0
  }
  return int(base_price_cents * rates.get(state, 0.05))