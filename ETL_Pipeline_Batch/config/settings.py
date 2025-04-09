# settings.py (updated)
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Snowflake Config
SNOWFLAKE_CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "role": os.getenv("SNOWFLAKE_ROLE")
}

# Paths (Windows-friendly)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARQUET_BASE_DIR = os.path.join(BASE_DIR, "Parquet_files")
DATA_DIR = os.path.join(BASE_DIR, "Data")
CALL_DATA_FILE = "Call_Data.csv"