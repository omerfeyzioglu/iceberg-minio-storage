#!/usr/bin/env python3
"""
Quick SQL Query Runner
Kullanim: query_text parametresini degistir ve calistir
"""

from pyspark.sql import SparkSession
import sys

def run_query(query):
    """SQL sorgusunu calistir"""
    spark = SparkSession.builder \
        .appName("Quick Query") \
        .getOrCreate()
    
    try:
        result = spark.sql(query)
        result.show(100, truncate=False)
        print(f"\nToplam satir: {result.count()}")
    except Exception as e:
        print(f"HATA: {str(e)}")
    finally:
        spark.stop()

if __name__ == "__main__":
    # Buraya istedigin SQL sorgusunu yaz
    
    # Secenekler (birini aktif et):
    
    # 1. Iceberg.db altindaki tum tablolari goster (ONERILEN)
    query = "SHOW TABLES FROM iceberg.db"
    
    # 2. Iceberg catalog'daki tum namespace'leri (database'leri) goster
    # query = "SHOW NAMESPACES FROM iceberg"
    
    # 3. Tum catalog'lari goster
    # query = "SHOW CATALOGS"
    
    # 4. Belirli bir tablonun yapisi (schema)
    # query = "DESCRIBE iceberg.db.transactions"
    
    # 5. Belirli bir tablodan veri cek
    # query = """
    #     SELECT 
    #         date,
    #         COUNT(*) as txn_count,
    #         ROUND(SUM(amount), 2) as total_revenue
    #     FROM iceberg.db.transactions
    #     GROUP BY date
    #     ORDER BY date DESC
    #     LIMIT 10
    # """
    
    # Komut satirindan sorgu alabilirsin (opsiyonel)
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    
    print(f"Calistirilan Sorgu:\n{query}\n")
    print("=" * 80)
    run_query(query)

