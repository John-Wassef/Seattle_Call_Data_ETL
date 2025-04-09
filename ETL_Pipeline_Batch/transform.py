from pyspark.sql import functions as fn
from pyspark.sql.functions import *
from pyspark.sql.types import StringType
from pyspark.sql import DataFrame
from typing import List

# UDF for timestamp conversion
def convert_to_24_hour(time_str: str) -> str:
    """Convert AM/PM timestamps to 24-hour format"""
    if time_str:
        try:
            date_part, time_part, period = time_str.split(" ")
            hours, minutes, seconds = time_part.split(":")
            if period == "PM" and hours != "12":
                hours = str(int(hours) + 12)
            elif period == "AM" and hours == "12":
                hours = "00"
            return f"{date_part} {hours}:{minutes}:{seconds}"
        except:
            return time_str
    return time_str

convert_to_24_hour_udf = fn.udf(convert_to_24_hour, StringType())

def fill_call_sign_at_scene_time(df: DataFrame) -> DataFrame:
    """Fill missing call_sign_at_scene_time values based on business rules"""
    return df.withColumn(
        "call_sign_at_scene_time",
        when(
            (col("first_response_at_scene_time") > col("call_sign_dispatch_time")) &
            (col("call_sign_at_scene_time").isNull()),
            col("first_response_at_scene_time")
        )
        .when(
            col("call_sign_at_scene_time").isNull(),
            col("call_sign_dispatch_time")
        )
        .otherwise(col("call_sign_at_scene_time"))
    )

def process_timestamps(df: DataFrame) -> DataFrame:
    """Process all timestamp columns in the DataFrame"""
    timestamp_columns = [
        "CAD Event Original Time Queued",
        "CAD Event Arrived Time",
        "Call Sign Dispatch Time",
        "First CARE Call Sign At Scene Time",
        "First CARE Call Sign Dispatch Time",
        "First Co-Response Call Sign At Scene Time",
        "First Co-Response Call Sign Dispatch Time",
        "First SPD Call Sign at Scene Time",
        "First SPD Call Sign Dispatch Time",
        "Last CARE Call Sign In-Service Time",
        "Last Co-Response Call Sign In-Service Time",
        "Last SPD Call Sign In-Service Time",
        "Call Sign at Scene Time",
        "Call Sign In-Service Time"
    ]

    # Extract event date
    df = df.withColumn("event_date", fn.substring(col(timestamp_columns[0]), 1, 10))

    # Convert timestamps
    for column in timestamp_columns:
        if column in df.columns:
            df = df.withColumn(column, convert_to_24_hour_udf(col(column)))
            df = df.withColumn(column, to_timestamp(col(column), "MM/dd/yyyy HH:mm:ss"))

    return df

def merge_response_times(df: DataFrame) -> DataFrame:
    """Merge response times from different agencies"""
    df = df.withColumn("first_response_at_scene_time",
                       coalesce(col("First SPD Call Sign at Scene Time"), 
                               col("First CARE Call Sign At Scene Time")))

    df = df.withColumn("first_response_dispatch_time",
                       coalesce(col("First SPD Call Sign Dispatch Time"), 
                               col("First CARE Call Sign Dispatch Time")))

    df = df.withColumn("last_response_in_service_time",
                       coalesce(col("Last SPD Call Sign In-Service Time"), 
                               col("Last CARE Call Sign In-Service Time")))

    df = df.withColumn("total_service_time_s",
                       coalesce(col("CARE Call Sign Total Service Time (s)"), 
                               col("SPD Call Sign Total Service Time (s)")))

    df = df.withColumn("dispatch_delay_time_s",
                       coalesce(col("First CARE Call Sign Dispatch Delay Time (s)"), 
                               col("First SPD Call Sign Dispatch Delay Time (s)")))

    df = df.withColumn("first_response_time_s",
                       coalesce(col("First CARE Call Sign Response Time (s)"), 
                               col("First SPD Call Sign Response Time (s)")))

    return df

def drop_columns(df: DataFrame) -> DataFrame:
    """Remove unnecessary columns"""
    columns_to_drop = [
        "First SPD Call Sign at Scene Time", "First CARE Call Sign At Scene Time",
        "First SPD Call Sign Dispatch Time", "First CARE Call Sign Dispatch Time",
        "Last SPD Call Sign In-Service Time", "Last CARE Call Sign In-Service Time",
        "CARE Call Sign Total Service Time (s)", "SPD Call Sign Total Service Time (s)",
        "First CARE Call Sign Dispatch Delay Time (s)", "First SPD Call Sign Dispatch Delay Time (s)",
        "First CARE Call Sign Response Time (s)", "First SPD Call Sign Response Time (s)",
        "Dispatch Longitude", "Dispatch Latitude", "Dispatch Reporting Area"
    ]
    return df.drop(*columns_to_drop)

def create_unit_id(df: DataFrame) -> DataFrame:
    """Create Unit ID by removing CAD Event Number from Call Sign Dispatch ID"""
    return df.withColumn("unit_id", 
                       fn.regexp_replace(col("Call Sign Dispatch ID"), 
                                        col("CAD Event Number").cast("string"), 
                                        ""))

def rename_columns(df: DataFrame) -> DataFrame:
    """Convert column names to snake_case"""
    def to_snake_case(column_name: str) -> str:
        column_name = column_name.replace("(s)", "s")
        column_name = column_name.replace(" ", "_").lower()
        column_name = column_name.replace("-", "_")
        return column_name

    new_columns = [to_snake_case(column) for column in df.columns]
    return df.toDF(*new_columns)

def drop_null_arrival_times(df: DataFrame) -> DataFrame:
    """Remove records with null arrival times"""
    return df.dropna(subset=["cad_event_arrived_time"])

def fill_missing_values(df: DataFrame) -> DataFrame:
    """Fill null values with defaults"""
    return df.fillna({"dispatch_sector": "UNKNOWN", "priority": -1})

def filter_events_with_null_in_service_time(df: DataFrame) -> DataFrame:
    """Filter out events with null in-service times"""
    events_with_nulls = df.filter(col("call_sign_in_service_time").isNull()) \
                         .select("cad_event_number") \
                         .distinct()
    return df.join(events_with_nulls, "cad_event_number", "left_anti")

def fill_call_sign_response_time(df: DataFrame) -> DataFrame:
    """Calculate response time if missing"""
    return df.withColumn(
        "call_sign_response_time_s",
        when(
            col("call_sign_response_time_s").isNull(),
            unix_timestamp(col("call_sign_at_scene_time")) - 
            unix_timestamp(col("cad_event_original_time_queued"))
        ).otherwise(col("call_sign_response_time_s"))
    )

def fill_first_response_at_scene_time(df: DataFrame) -> DataFrame:
    """Fill missing first response times based on business rules"""
    return df.withColumn(
        "first_response_at_scene_time",
        when(
            (col("call_sign_at_scene_time") > col("call_sign_dispatch_time")) &
            (col("first_response_at_scene_time").isNull()),
            col("call_sign_at_scene_time")
        )
        .when(
            col("first_response_at_scene_time").isNull(),
            col("call_sign_dispatch_time")
        )
        .otherwise(col("first_response_at_scene_time"))
    )

def fill_first_response_time(df: DataFrame) -> DataFrame:
    """Fill missing first response times and calculate duration"""
    df = df.withColumn(
        "first_response_at_scene_time",
        when(
            (to_timestamp(col("call_sign_at_scene_time")) > 
            to_timestamp(col("call_sign_dispatch_time"))) &
            col("first_response_at_scene_time").isNull(),
            col("call_sign_at_scene_time")
        ).when(
            col("first_response_at_scene_time").isNull(),
            col("call_sign_dispatch_time")
        ).otherwise(col("first_response_at_scene_time"))
    )

    df = df.withColumn(
        "first_response_time_s",
        when(
            col("first_response_time_s").isNull(),
            unix_timestamp(col("first_response_at_scene_time")) - 
            unix_timestamp(col("cad_event_original_time_queued"))
        ).otherwise(col("first_response_time_s"))
    )
    return df

def add_keys_for_star_schema(df: DataFrame) -> DataFrame:
    """
    Add surrogate keys for star schema dimensions
    Now using consistent naming convention (dim_ prefix for all dimension keys)
    """
    return (df
        .withColumn("dim_care_spd_id", monotonically_increasing_id())  # SK for Dim_Care_SPD
        .withColumn("dim_co_response_id", monotonically_increasing_id())  # SK for Dim_Co_Response
        .withColumn("dim_cad_event_id", monotonically_increasing_id())  # SK for Dim_CAD_Event
        .withColumn("dim_location_id", monotonically_increasing_id())  # SK for Dim_Location
        .withColumn("dim_call_sign_id", monotonically_increasing_id())  # SK for Dim_Call_Sign
    )

def transform_data(df: DataFrame) -> DataFrame:
    """Orchestrate all transformation steps"""
    df = process_timestamps(df)
    df = merge_response_times(df)
    df = drop_columns(df)
    df = create_unit_id(df)
    df = rename_columns(df)
    df = fill_call_sign_at_scene_time(df)
    df = fill_missing_values(df)
    df = drop_null_arrival_times(df)
    df = filter_events_with_null_in_service_time(df)
    df = fill_call_sign_response_time(df)
    df = fill_first_response_time(df)
    df = add_keys_for_star_schema(df)
    
    # Final validation
    required_columns = [
        'call_sign_dispatch_id', 'call_sign_dispatch_time',
        'dim_care_spd_id', 'dim_co_response_id', 'dim_cad_event_id',
        'dim_location_id', 'dim_call_sign_id'
    ]
    
    for col_name in required_columns:
        if col_name not in df.columns:
            raise ValueError(f"Required column {col_name} missing after transformations")
    
    return df