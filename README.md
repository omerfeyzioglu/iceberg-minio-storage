# Apache Iceberg on MinIO with Spark

Local data-lake sandbox: **Apache Spark** reads and writes **Apache Iceberg** tables stored in **MinIO** over the S3A protocol. Two MinIO deployments model **hot** and **cold** tiers; lifecycle (ILM) rules can transition older objects to the cold cluster while queries keep using the same Iceberg table path.

**Stack:** Spark 3.5 (master + worker), Iceberg 1.5.x (Hadoop catalog), MinIO (`mc` for ops), PySpark scripts.

## Requirements

- Docker and Docker Compose
- JARs under `jars/`: `iceberg-spark-runtime-3.5_2.12-1.5.2.jar`, `aws-java-sdk-bundle-1.12.262.jar`, `hadoop-aws-3.3.4.jar` (Maven Central; optional helper: `scripts/download-jars.sh`)

## Quick start

```bash
docker compose up -d
```

Then configure MinIO aliases, buckets, and the remote cold tier, and run ingestion (example):

```bash
docker exec minio-mc mc alias set hot http://minio-hot:9000 minioadmin minioadmin
docker exec minio-mc mc alias set cold http://minio-cold:9000 minioadmin minioadmin
docker exec minio-mc mc mb hot/iceberg-warehouse
docker exec minio-mc mc mb cold/iceberg-cold-tier
docker exec minio-mc mc admin tier add minio hot COLDTIER --endpoint http://minio-cold:9000 \
  --access-key minioadmin --secret-key minioadmin --bucket iceberg-cold-tier --prefix "db/transactions/"
docker exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /scripts/ingest_data.py
```

**ILM (example):** move data from hot to cold after policy criteria are met:

```text
mc ilm add hot/iceberg-warehouse --transition-days 30 --storage-class COLDTIER --prefix "db/transactions/data/"
```

Adjust `--transition-days` to your retention window. Iceberg maintenance (e.g. compaction, snapshot expiration) uses Spark SQL `CALL iceberg.system.*`; catalog and S3A settings live in `spark-config/spark-defaults.conf`.

## Ports

| Service      | Ports        |
|-------------|--------------|
| MinIO hot   | 9000, 9001   |
| MinIO cold  | 9100, 9101   |
| Spark master| 8080, 7077, 4040 |

## Scripts

- `scripts/ingest_data.py` — create table and ingest data  
- `scripts/query_analysis.py` — sample analytics  
- `scripts/quick_query.py` — quick SQL-style checks  

## Scope

This repository is for **local experimentation**. Production deployments need TLS, authentication, backups, and observability on top of this layout.
