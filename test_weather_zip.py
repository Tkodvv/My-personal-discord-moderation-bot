#!/usr/bin/env python3
"""
Weather Command Zip Code Test
This script demonstrates the new zip code support in the weather command.
"""

def format_location_for_api(location: str) -> str:
    """Format location input for OpenWeatherMap API."""
    location = location.strip()
    
    # Check if it looks like a zip code (numeric, optionally with country code)
    if ',' in location:
        # Already has country code (e.g., "10001,US" or "SW1A 1AA,GB")
        return f"zip={location}"
    elif location.replace(' ', '').isdigit():
        # Numeric only - assume US zip code
        return f"zip={location},US"
    elif len(location) == 5 and location.isdigit():
        # 5-digit number - US zip code
        return f"zip={location},US"
    else:
        # Assume it's a city name
        return f"q={location}"

def test_location_formats():
    """Test different location format inputs."""
    test_cases = [
        "New York",           # City name
        "London",             # City name
        "10001",              # US ZIP code
        "90210",              # US ZIP code  
        "10001,US",           # ZIP with country
        "SW1A 1AA,GB",        # UK postcode
        "M5V 3L9,CA",         # Canadian postal code
        "75001,FR",           # French postal code
        "Tokyo"               # International city
    ]
    
    print("Weather Command - Location Format Testing")
    print("=" * 50)
    
    for location in test_cases:
        api_param = format_location_for_api(location)
        url = f"http://api.openweathermap.org/data/2.5/weather?{api_param}&appid=YOUR_API_KEY&units=metric"
        print(f"Input: '{location}' -> API URL: {url}")
    
    print("\n" + "=" * 50)
    print("✅ All location formats processed successfully!")

if __name__ == "__main__":
    test_location_formats()
