from pyspark.sql import SparkSession, DataFrame
from pyspark.storagelevel import StorageLevel
import os
from config.settings import DATA_DIR, CALL_DATA_FILE
import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def initialize_spark(app_name: str = "CallDataETL") -> SparkSession:
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.jars.packages", "org.apache.spark:spark-avro_2.12:3.5.0") \
        .config("spark.driver.memory", "4g") \
        .config("spark.executor.memory", "4g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .config("spark.network.timeout", "1200s") \
        .config("spark.executor.heartbeatInterval", "300s") \
        .config("spark.sql.files.maxPartitionBytes", "64m") \
        .config("spark.driver.maxResultSize", "2g") \
        .config("spark.ui.showConsoleProgress", "false") \
        .getOrCreate()

def safe_extract(
    spark: SparkSession,
    file_path: str,
    sample_ratio: float = 0.01,
    max_rows: Optional[int] = None
) -> DataFrame:
    """
    Safely extract data from large CSV with memory protection
    
    Args:
        spark: Active Spark session
        file_path: Path to CSV file
        sample_ratio: Fraction of data to sample for schema
        max_rows: Maximum rows to read (None for all)
        
    Returns:
        Spark DataFrame with the loaded data
    """
    try:
        logger.info(f"Beginning extraction from {file_path}")
        
        # Step 1: Sample to infer schema (memory efficient)
        sample_df = spark.read \
            .option("header", "true") \
            .option("inferSchema", "true") \
            .option("samplingRatio", str(sample_ratio)) \
            .csv(file_path)
            
        schema = sample_df.schema
        logger.info("Schema inference completed")

        # Step 2: Read full data with known schema
        reader = spark.read \
            .option("header", "true") \
            .schema(schema) \
            .option("mode", "DROPMALFORMED") \
            .option("encoding", "UTF-8") \
            .option("nullValue", "") \
            .option("nanValue", "")
            
        if max_rows:
            reader = reader.option("maxRows", max_rows)
            logger.info(f"Limiting extraction to {max_rows} rows")
            
        df = reader.csv(file_path)
        
        # Use disk persistence to avoid memory overload
        df.persist(StorageLevel.DISK_ONLY)
        logger.info("Data loading completed")
        
        return df
        
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to extract data: {str(e)}") from e

def extract_data(spark: SparkSession) -> DataFrame:
    """
    Main extraction function with error handling
    
    Args:
        spark: Initialized Spark session
        
    Returns:
        Loaded DataFrame
    """
    file_path = os.path.join(DATA_DIR, CALL_DATA_FILE)
    
    if not os.path.exists(file_path):
        error_msg = f"Data file not found at: {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    try:
        # First attempt with default settings
        return safe_extract(spark, file_path)
        
    except Exception as first_error:
        logger.warning(f"Initial extraction failed, retrying with safety limits: {str(first_error)}")
        
        try:
            # Fallback: Process in chunks with row limit
            return safe_extract(
                spark,
                file_path,
                sample_ratio=0.05,
                max_rows=500000  # Limit to 500k rows
            )
        except Exception as fallback_error:
            logger.critical("All extraction methods failed")
            raise RuntimeError("Failed to extract data after multiple attempts") from fallback_error

def validate_data(df: DataFrame) -> bool:
    """
    Basic DataFrame validation
    
    Args:
        df: Loaded DataFrame to validate
        
    Returns:
        True if data appears valid
    """
    try:
        if df.rdd.isEmpty():
            logger.error("Empty DataFrame detected")
            return False
            
        required_columns = ["CAD Event Number", "Call Type", "Priority"]
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return False
                
        logger.info("Data validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return False