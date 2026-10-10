import csv
import os

from db_queries import DBManager
from slugify import slugify

# Define the CSV file path
DATA_FILE = os.path.join(os.path.dirname(__file__), "data/location.csv")


def process_csv():
    """Read CSV and prepare bulk data for insertion."""
    new_countries = set()
    new_states = set()
    new_cities = set()

    with open(DATA_FILE, "r", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            country_name, state_name, city_name = (
                row.get("country_name", "").strip(),
                row.get("state_name", "").strip(),
                row.get("name", "").strip(),
            )

            if not (country_name and state_name and city_name):
                print(f"Skipping row due to missing data: {row}")
                continue

            country_slug = slugify(country_name)
            state_slug = slugify(f"{state_name}-{country_name}")
            city_slug = slugify(f"{city_name}-{state_name}")

            new_countries.add((country_name, country_slug))
            new_states.add((state_name, state_slug, country_slug))
            new_cities.add((city_name, city_slug, state_slug))

    return new_countries, new_states, new_cities


def insert_data():
    """Insert parsed data into the database using DBManager."""
    db_manager = DBManager()

    try:
        new_countries, new_states, new_cities = process_csv()
        db_manager.insert_location(new_countries, new_states, new_cities)
        print("Data inserted successfully.")
    except Exception as e:
        print(f"Error inserting data: {e}")
        raise e


if __name__ == "__main__":
    print("Starting data import...")
    insert_data()
    print("Data import completed successfully!")
