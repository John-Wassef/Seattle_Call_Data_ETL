from extract import extract_data, initialize_spark
from transform import transform_data
from load import save_to_parquet, load_to_snowflake
from pyspark.sql import SparkSession

def run_etl():
    spark = None
    try:
        # Initialize
        spark = initialize_spark()
        
        # ETL Pipeline
        print("[1/3] Extracting data...")
        raw_df = extract_data(spark)
        
        print("[2/3] Transforming data...")
        transformed_df = transform_data(raw_df)
        
        print("[3/3] Loading data...")
        save_to_parquet(transformed_df)
        load_to_snowflake()
        
        print("✅ ETL Pipeline completed!")
    except Exception as e:
        print(f"❌ Pipeline failed: {str(e)}")
        raise
    finally:
        if spark:
            spark.stop()

if __name__ == "__main__":
    run_etl()