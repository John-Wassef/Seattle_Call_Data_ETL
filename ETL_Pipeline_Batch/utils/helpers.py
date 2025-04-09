from pyspark.sql import DataFrame
from pprint import pprint
import pyarrow.parquet as pq
import os
import glob

def print_step(message: str, emoji: str = "🔹") -> None:
    """Print formatted step message with emoji"""
    print(f"\n{'='*50}")
    print(f"{emoji} {message}")
    print(f"{'='*50}")

def get_table_name_from_dir(dir_name: str) -> str:
    """Convert directory name to table name"""
    return dir_name.replace("_parquet", "").lower()

def verify_parquet_file(file_path: str) -> tuple:
    """Verify Parquet file integrity"""
    try:
        table = pq.read_table(file_path)
        return True, table.schema, table.num_rows
    except Exception as e:
        return False, str(e), 0