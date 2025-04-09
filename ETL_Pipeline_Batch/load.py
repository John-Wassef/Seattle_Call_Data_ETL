import snowflake.connector
import pyarrow.parquet as pq
import os
import glob
from pyspark.sql import DataFrame
from config.settings import SNOWFLAKE_CONFIG, PARQUET_BASE_DIR
from utils.helpers import print_step, get_table_name_from_dir, verify_parquet_file
from typing import Dict, List
from pprint import pprint
from pyspark.sql.functions import col

def setup_snowflake_environment(cur) -> str:
    """Create Snowflake file format and stage"""
    print_step("Setting up Snowflake environment", "❄️")

    # Create file format
    cur.execute("""
        CREATE OR REPLACE FILE FORMAT parquet_format
        TYPE = 'PARQUET'
        COMPRESSION = 'AUTO'
    """)

    # Create stage
    stage_name = f"{SNOWFLAKE_CONFIG['database']}.{SNOWFLAKE_CONFIG['schema']}.parquet_stage"
    cur.execute(f"""
        CREATE OR REPLACE STAGE {stage_name}
        FILE_FORMAT = parquet_format
    """)
    print(f"Created stage: {stage_name}")
    return stage_name

def process_parquet_file(cur, stage_name: str, table_dir: str) -> bool:
    """Process a single table directory and load to Snowflake"""
    table_name = get_table_name_from_dir(table_dir)
    parquet_files = glob.glob(f"{PARQUET_BASE_DIR}/{table_dir}/part-*.parquet")

    if not parquet_files:
        print(f"⚠️  No Parquet files found in {table_dir}")
        return False

    file_path = parquet_files[0]
    filename = os.path.basename(file_path)

    print_step(f"Processing {table_name}", "🔄")

    try:
        # 1. Verify Parquet file
        is_valid, schema, num_rows = verify_parquet_file(file_path)
        if not is_valid:
            raise ValueError(f"Invalid Parquet file: {schema}")

        # 2. Upload file
        print("📤 Uploading to stage...")
        put_cmd = f"""
        PUT 'file://{file_path.replace(os.sep, "/")}' @{stage_name}/{filename}
        AUTO_COMPRESS = FALSE
        OVERWRITE = TRUE
        """
        cur.execute(put_cmd)

        # 3. Create table
        print("🛠️  Creating table...")
        cur.execute(f"""
                CREATE OR REPLACE TABLE {SNOWFLAKE_CONFIG['database']}.{SNOWFLAKE_CONFIG['schema']}.{table_name}
                USING TEMPLATE (
                    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
                    FROM TABLE(
                        INFER_SCHEMA(
                            LOCATION => '@{stage_name}/{filename}',
                            FILE_FORMAT => 'parquet_format'
                        )
                    )
                )
            """)

        # 4. Load data
        print("⬆️  Loading data...")
        cur.execute(f"""
            COPY INTO {SNOWFLAKE_CONFIG['database']}.{SNOWFLAKE_CONFIG['schema']}.{table_name}
            FROM @{stage_name}/{filename}
            MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            PURGE = TRUE
        """)

        # 5. Verify
        cur.execute(f"SELECT COUNT(*) FROM {SNOWFLAKE_CONFIG['database']}.{SNOWFLAKE_CONFIG['schema']}.{table_name}")
        count = cur.fetchone()[0]
        print(f"\n✅ Successfully loaded {count:,} rows into {table_name}")
        return True

    except Exception as e:
        print(f"\n❌ Error loading {table_name}: {str(e)}")
        return False

def save_to_parquet(df: DataFrame, output_dir: str = PARQUET_BASE_DIR) -> None:
    """Save ALL tables to Parquet files with star schema relationships"""
    print_step("SAVING STAR SCHEMA TABLES TO PARQUET")

    tables = {
        "fact_call": {
            "columns": [
                "call_sign_dispatch_time",
                "call_sign_dispatch_delay_time_s",
                "call_sign_response_time_s",
                "call_sign_total_service_time_s",
                "dim_care_spd_id",
                "dim_co_response_id",
                "dim_cad_event_id",
                "dim_location_id",
                "dim_call_sign_id"
            ]
        },
        "dim_care_spd": {
            "columns": [
                "call_sign_dispatch_id",
                "dim_care_spd_id",
                "first_response_dispatch_time",
                "last_response_in_service_time",
                "first_response_time_s",
                "dispatch_delay_time_s",
                "first_response_at_scene_time"
            ]
        },
        "dim_co_response": {
            "columns": [
                "call_sign_dispatch_id",
                "dim_co_response_id",
                "first_co_response_call_sign_at_scene_time",
                "first_co_response_call_sign_dispatch_time",
                "last_co_response_call_sign_in_service_time",
                "first_co_response_call_sign_dispatch_delay_time_s",
                "first_co_response_call_sign_response_time_s"
            ]
        },
        "dim_cad_event": {
            "columns": [
                "call_sign_dispatch_id",
                "dim_cad_event_id",
                "priority",
                "cad_event_number",
                "cad_event_clearance_description",
                "call_type",
                "initial_call_type",
                "final_call_type",
                "cad_event_response_category",
                "cad_event_original_time_queued",
                "call_type_received_classification",
                "cad_event_arrived_time",
                "call_type_indicator",
                "unit_id",
                "cad_event_first_response_time_s"
            ]
        },
        "dim_location": {
            "columns": [
                "call_sign_dispatch_id",
                "dim_location_id",
                "dispatch_precinct",
                "dispatch_sector",
                "dispatch_beat",
                "dispatch_neighborhood"
            ]
        },
        "dim_call_sign": {
            "columns": [
                "call_sign_dispatch_id",
                "dim_call_sign_id",
                "call_sign_dispatch_time",
                "call_sign_at_scene_time",
                "call_sign_in_service_time"
            ]
        }
    }

    os.makedirs(output_dir, exist_ok=True)

    for table_name, config in tables.items():
        table_dir = os.path.join(output_dir, f"{table_name}_parquet")
        print(f"\n📁 Saving {table_name} to {table_dir}...")

        # Select columns for the current table
        df_table = df.select(config["columns"])

        # Write as single Parquet file
        df_table.coalesce(1).write.mode("overwrite").parquet(table_dir)

        # Verify
        written_files = glob.glob(f"{table_dir}/part-*.parquet")
        if written_files:
            parquet_table = pq.read_table(written_files[0])
            print(f"✅ {table_name}: {parquet_table.num_rows:,} rows saved")
            print(f"   Schema: {parquet_table.schema.names[:3]}...")
        else:
            print(f"❌ Failed to save {table_name}")

    print_step("STAR SCHEMA SAVE COMPLETE")

def load_to_snowflake() -> None:
    """Load ALL Parquet tables to Snowflake"""
    print_step("LOADING ALL TABLES TO SNOWFLAKE")

    conn = None
    try:
        conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
        cur = conn.cursor()

        # Setup environment
        stage_name = setup_snowflake_environment(cur)

        # Find all tables
        table_dirs = [
            d for d in os.listdir(PARQUET_BASE_DIR)
            if os.path.isdir(os.path.join(PARQUET_BASE_DIR, d))
            and d.endswith('_parquet')
        ]

        print(f"\n🔍 Found {len(table_dirs)} tables to load:")
        pprint(sorted(table_dirs))

        # Process each table
        success_count = 0
        for table_dir in sorted(table_dirs):
            if process_parquet_file(cur, stage_name, table_dir):
                success_count += 1

        # Results
        print_step("LOAD RESULTS")
        if success_count == len(table_dirs):
            print(f"🎉 Successfully loaded ALL {success_count} tables")
        else:
            print(f"⚠️  Loaded {success_count}/{len(table_dirs)} tables")
            print("Check above logs for errors")

    except Exception as e:
        print(f"\n❌ Snowflake connection error: {str(e)}")
        raise
    finally:
        if conn:
            cur.close()
            conn.close()