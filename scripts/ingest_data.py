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
import argparse
import os
import base64

def create_spark_session():
    return SparkSession.builder \
        .appName("Iceberg Data Ingestion") \
        .getOrCreate()

def create_sample_data(spark, num_records=10000, date_offset=0, payload_bytes=0, random_payload=False):

    target_date = datetime.now() - timedelta(days=date_offset)
    
    data = []
    categories = ['Electronics', 'Clothing', 'Food', 'Books', 'Sports']
    regions = ['North', 'South', 'East', 'West', 'Central']
    
    payload_unit = "X" * max(0, min(payload_bytes, 1024))  # build in chunks to avoid huge string ops
    repeats = 0 if payload_bytes <= 0 else max(1, payload_bytes // max(1, len(payload_unit)))

    for i in range(num_records):
        # construct payload lazily to avoid allocating giant single string repeatedly
        if payload_bytes > 0:
            if random_payload:
                # generate random bytes and base64-encode to printable string with similar size
                raw = os.urandom(payload_bytes)
                payload = base64.b64encode(raw).decode('ascii')
            else:
                payload = payload_unit * repeats
        else:
            payload = None
        data.append({
            'transaction_id': f'TXN{target_date.strftime("%Y%m%d")}_{i:06d}',
            'category': random.choice(categories),
            'region': random.choice(regions),
            'amount': round(random.uniform(10, 1000), 2),
            'quantity': random.randint(1, 100),
            'date': target_date.date(),
            'payload': payload
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
            date DATE,
            payload STRING
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
    print(" Tablo kontrol edildi/oluşturuldu: iceberg.db.transactions")

def ingest_data(spark, date_offset=0, num_records=10000, payload_bytes=0, compression="zstd", target_file_size_bytes=134217728, repartition=None, random_payload=False, disable_parquet_dictionary=False):
    """
    Veri ingestion
    
    Args:
        spark: SparkSession
        date_offset: 0=bugün, 1=dün, 2=2 gün önce, vb.
        num_records: Kayıt sayısı
    """
    target_date = (datetime.now() - timedelta(days=date_offset)).date()
    
    print(f"\n Veri ingestion başlatılıyor...")
    print(f"   Tarih: {target_date}")
    print(f"   Kayıt sayısı: {num_records}")
    print(f"   Payload bytes/row: {payload_bytes}")
    print(f"   Compression: {compression}")
    print(f"   Random payload: {random_payload}")
    print(f"   Disable Parquet dictionary: {disable_parquet_dictionary}")
    
    # Veri oluştur
    df = create_sample_data(spark, num_records, date_offset, payload_bytes, random_payload)

    # Opsiyonel repartition (büyük dosya üretmeye yardım eder)
    if repartition is not None and repartition > 0:
        df = df.repartition(repartition)

    # Yazım öncesi tablo yazma özelliklerini ayarla
    codec = 'uncompressed' if compression in [None, '', 'none', 'uncompressed'] else compression
    spark.sql(f"""
        ALTER TABLE iceberg.db.transactions SET TBLPROPERTIES (
          'write.parquet.compression-codec' = '{codec}',
          'write.target-file-size-bytes' = '{int(target_file_size_bytes)}',
          'write.parquet.dictionary.enabled' = '{'false' if disable_parquet_dictionary else 'true'}'
        )
    """)
    
    # Tabloya yaz
    df.writeTo("iceberg.db.transactions").append()
    
    print(f" {num_records} kayıt başarıyla yazıldı!")
    
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
    
    print("\n İstatistikler:")
    stats.show()

def show_table_info(spark):
    """Tablo bilgilerini göster"""
    print("\n Tablo Metadata:")
    spark.sql("DESCRIBE EXTENDED iceberg.db.transactions").show(truncate=False)
    
    print("\n Partition Özeti:")
    spark.sql("""
        SELECT 
            date,
            COUNT(*) as record_count,
            SUM(amount) as total_amount
        FROM iceberg.db.transactions
        GROUP BY date
        ORDER BY date DESC
    """).show()
    
    print("\n Tablo Dosyaları:")
    spark.sql("SELECT * FROM iceberg.db.transactions.files").show(truncate=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Iceberg bulk ingestion")
    parser.add_argument('--clean', action='store_true', help='Tabloyu drop + recreate')
    parser.add_argument('--num-records', type=int, default=10000, help='Kayıt sayısı')
    parser.add_argument('--date-offset', type=int, default=0, help='0=bugün, 1=dün, ...')
    parser.add_argument('--payload-bytes', type=int, default=0, help='Satır başına ek string payload boyutu')
    parser.add_argument('--compression', type=str, default='zstd', help='zstd|gzip|none')
    parser.add_argument('--target-file-size-bytes', type=int, default=134217728, help='Hedef dosya boyutu (bytes)')
    parser.add_argument('--repartition', type=int, default=None, help='Yazmadan önce repartition N')
    parser.add_argument('--random-payload', action='store_true', help='Her satır için rastgele payload üret')
    parser.add_argument('--disable-parquet-dictionary', action='store_true', help='Parquet dictionary encoding kapat')

    args = parser.parse_args()

    print(" Iceberg Data Ingestion Script")
    print("=" * 50)

    spark = create_spark_session()

    try:
        if args.clean:
            # Drop + recreate
            spark.sql("DROP TABLE IF EXISTS iceberg.db.transactions")
            initialize_table_if_not_exists(spark)
        else:
            initialize_table_if_not_exists(spark)

        ingest_data(
            spark,
            date_offset=args.date_offset,
            num_records=args.num_records,
            payload_bytes=args.payload_bytes,
            compression=args.compression,
            target_file_size_bytes=args.target_file_size_bytes,
            repartition=args.repartition,
            random_payload=args.random_payload,
            disable_parquet_dictionary=args.disable_parquet_dictionary,
        )

        show_table_info(spark)

        print("\nIngestion tamamlandı")
    finally:
        spark.stop()

