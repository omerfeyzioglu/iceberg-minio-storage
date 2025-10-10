#!/usr/bin/env python3
"""
Iceberg Data Ingestion Script
Veriyi tarih bazlı partition ile HOT tier'a yazar
ZSTD Level 3 compression kullanır
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_date, lit, rand, current_timestamp
from datetime import datetime, timedelta
import random

def create_spark_session():
    """Iceberg + MinIO yapılandırmalı Spark session"""
    return SparkSession.builder \
        .appName("Iceberg Data Ingestion") \
        .config("spark.jars", "/opt/spark/jars/custom/iceberg-spark-runtime-3.5_2.12-1.5.2.jar,"
                              "/opt/spark/jars/custom/aws-java-sdk-bundle-1.12.262.jar,"
                              "/opt/spark/jars/custom/hadoop-aws-3.3.4.jar") \
        .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.iceberg.type", "hadoop") \
        .config("spark.sql.catalog.iceberg.warehouse", "s3a://iceberg-warehouse/") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio-hot:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.defaultCatalog", "iceberg") \
        .getOrCreate()

def create_sample_data(spark, num_records=10000, date_offset=0):
    """
    Örnek veri oluştur
    
    Args:
        spark: SparkSession
        num_records: Oluşturulacak kayıt sayısı
        date_offset: Bugünden kaç gün geriye gidilecek (0=bugün, 1=dün, vb.)
    """
    target_date = datetime.now() - timedelta(days=date_offset)
    
    # Örnek veri
    data = []
    categories = ['Electronics', 'Clothing', 'Food', 'Books', 'Sports']
    regions = ['North', 'South', 'East', 'West', 'Central']
    
    for i in range(num_records):
        data.append({
            'transaction_id': f'TXN{target_date.strftime("%Y%m%d")}_{i:06d}',
            'category': random.choice(categories),
            'region': random.choice(regions),
            'amount': round(random.uniform(10, 1000), 2),
            'quantity': random.randint(1, 100),
            'date': target_date.date()
        })
    
    return spark.createDataFrame(data)

def initialize_table_if_not_exists(spark):
    """Tablo yoksa oluştur"""
    spark.sql("""
        CREATE TABLE IF NOT EXISTS iceberg.db.transactions (
            transaction_id STRING,
            category STRING,
            region STRING,
            amount DOUBLE,
            quantity INT,
            date DATE
        )
        USING iceberg
        PARTITIONED BY (date)
        TBLPROPERTIES (
            'format-version' = '2',
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'zstd',
            'write.parquet.compression-level' = '3',
            'write.metadata.compression-codec' = 'gzip',
            'write.target-file-size-bytes' = '134217728'
        )
    """)
    print("✅ Tablo kontrol edildi/oluşturuldu: iceberg.db.transactions")

def ingest_data(spark, date_offset=0, num_records=10000):
    """
    Veri ingestion
    
    Args:
        spark: SparkSession
        date_offset: 0=bugün, 1=dün, 2=2 gün önce, vb.
        num_records: Kayıt sayısı
    """
    target_date = (datetime.now() - timedelta(days=date_offset)).date()
    
    print(f"\n📊 Veri ingestion başlatılıyor...")
    print(f"   Tarih: {target_date}")
    print(f"   Kayıt sayısı: {num_records}")
    print(f"   Compression: ZSTD Level 3")
    
    # Veri oluştur
    df = create_sample_data(spark, num_records, date_offset)
    
    # Tabloya yaz
    df.writeTo("iceberg.db.transactions") \
        .option("write-format", "parquet") \
        .option("compression-codec", "zstd") \
        .option("compression-level", "3") \
        .append()
    
    print(f"✅ {num_records} kayıt başarıyla yazıldı!")
    
    # İstatistikler
    stats = spark.sql(f"""
        SELECT 
            date,
            COUNT(*) as record_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount
        FROM iceberg.db.transactions
        WHERE date = DATE'{target_date}'
        GROUP BY date
    """)
    
    print("\n📈 İstatistikler:")
    stats.show()

def show_table_info(spark):
    """Tablo bilgilerini göster"""
    print("\n📋 Tablo Metadata:")
    spark.sql("DESCRIBE EXTENDED iceberg.db.transactions").show(truncate=False)
    
    print("\n📊 Partition Özeti:")
    spark.sql("""
        SELECT 
            date,
            COUNT(*) as record_count,
            SUM(amount) as total_amount
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date DESC
    """).show()
    
    print("\n📁 Tablo Dosyaları:")
    spark.sql("SELECT * FROM iceberg.db.transactions.files").show(truncate=False)

if __name__ == "__main__":
    print("🚀 Iceberg Data Ingestion Script")
    print("=" * 50)
    
    spark = create_spark_session()
    
    try:
        # Tabloyu oluştur/kontrol et
        initialize_table_if_not_exists(spark)
        
        # Bugünün verisi
        print("\n" + "=" * 50)
        print("📅 BUGÜNÜN VERİSİ (T+0)")
        print("=" * 50)
        ingest_data(spark, date_offset=0, num_records=10000)
        
        # İsteğe bağlı: Geçmiş veriler (test için)
        # Dünün verisi
        print("\n" + "=" * 50)
        print("📅 DÜNÜN VERİSİ (T+1) - Test amaçlı")
        print("=" * 50)
        ingest_data(spark, date_offset=1, num_records=8000)
        
        # 2 gün öncenin verisi
        print("\n" + "=" * 50)
        print("📅 2 GÜN ÖNCENİN VERİSİ (T+2) - Test amaçlı")
        print("=" * 50)
        ingest_data(spark, date_offset=2, num_records=6000)
        
        # Tablo bilgileri
        show_table_info(spark)
        
        print("\n✨ Veri ingestion tamamlandı!")
        print("\n💡 Not: MinIO ILM rule 1 gün sonra eski veriyi COLD tier'a taşıyacak")
        
    finally:
        spark.stop()

